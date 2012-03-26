import logging
log = logging.getLogger()
log.setLevel(logging.DEBUG)

sh = logging.StreamHandler()

formatter = logging.Formatter('[%(asctime)s] %(levelname)s: {%(funcName)s} %(message)s')
#fh.setFormatter(formatter)
sh.setFormatter(formatter)
#log.addHandler(fh)
log.addHandler(sh)

import json
import datetime
now = datetime.datetime.now
import random
log.info("Starting up..")

import sqlalchemy

from sqlalchemy import create_engine
with open("database", "r") as f: db = f.read()
engine = create_engine(db, echo=False)

from sqlalchemy.orm import sessionmaker, scoped_session

from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()

from sqlalchemy import Column, Integer, String, Unicode, LargeBinary, Boolean, Date, DateTime, Text, Enum
from sqlalchemy import Table, ForeignKey, TypeDecorator
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm import relationship, backref
from sqlalchemy.orm.session import make_transient

class JSONEncodedDict(TypeDecorator):
    impl = String(512)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if not value:
            return None
        return json.loads(value)

class Item(Base):
    __tablename__ = "tc_items"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    desc = Column(String(512), nullable=False)
    category = Column(Enum("unspecified", "equip", "usable", "trash"), nullable=False)
    questable = Column(Boolean, nullable=False)
    effect = Column(Enum("none", "passive"), nullable=False, default="none")
    parameter = Column(JSONEncodedDict, nullable=False)

class Room(Base):
    __tablename__ = "tc_rooms"
    id = Column(Integer, primary_key=True)
    discriminator = Column('type', String(32))
    __mapper_args__ = {'polymorphic_on': discriminator}
    
    def begin_session(self, character):
        self.character = character
    
    def success(self, message=None):
        if message: self.character.messages.append(message)
        self.character.room_state = "success"
        self.character.choices = [] # XXX What if there are non-room choices like loot corpse?  Add them afterwards?  Adding proceed outside of here for now.
        # XXX ^ doesn't seem to change anything at all anyway currently!!!
    
    def failure(self, message=None):
        if message: self.character.messages.append(message)
        self.character.room_state = "failure"
        self.character.choices = []
        
    def action(self, choice):
        raise ValueError("This room type does not define choices")
        
    #stamp = relationship("Stamp", uselist=False, backref="parent")

class PuzzleDoorRoom(Room):
    __tablename__ = "tc_rooms_puzzle_door"
    __mapper_args__ = {'polymorphic_identity': 'puzzle_door'}
    id = Column(Integer, ForeignKey('tc_rooms.id'), primary_key=True)
    
    problem_solving = Column(Integer)
    brute_forcing = Column(Integer)
    pathfinding = Column(Integer)
    damage = Column(Integer)
    door = Column(String(32)) # Enum?
    
    def begin_session(self, character):
        self.character = character
        if self.character.room_state == "none":
            self.character.choices += ["solve", "force", "safe_path"]
        
    def enter(self):
        self.character.messages.append("You're in a puzzle door room.  [problem_solving = {}]".format(self.problem_solving))
        
    def failure(self, message=None):
        message += "  You took {} damage!".format(self.damage)
        if message: self.character.messages.append(message)
        self.character.room_state = "failure"
        self.character.choices = []
        self.character.hp -= 20
        
    def action(self, choice):
        if choice == "solve":
            if self.character.problem_solving >= self.problem_solving:
                self.success("You've solved the door!")
            else:
                self.failure("Failed to solve the door!")
        elif choice == "force":
            if self.character.brute_forcing >= self.brute_forcing:
                self.success("You've solved the door by brute forcing!")
            else:
                self.failure("Failed to brute force!")
        elif choice == "safe_path":
            if self.character.pathfinding >= self.pathfinding:
                self.success("You've found a way to get past the door!")
            else:
                self.failure("Failed!")
        else:
            raise ValueError("Invalid choice")
            
class TreasureRoom(Room):
    __tablename__ = "tc_rooms_treasure_rooms"
    __mapper_args__ = {'polymorphic_identity': 'treasure_room'}
    id = Column(Integer, ForeignKey('tc_rooms.id'), primary_key=True)
    
    gold = Column(Integer)
    
    def begin_session(self, character):
        self.character = character
        if self.character.room_state == "none":
            self.character.choices += ["pick_up"]
        
    def enter(self):
        self.character.messages.append("You're in a treasure room.  There is {} gold.".format(self.gold))
        
    def action(self, choice):
        if choice == "pick_up":
            self.character.gold += self.gold
            self.success("You've picked up the gold!")
        else:
            raise ValueError("Invalid choice")

class InventoryItem(Base):
    __tablename__ = 'tc_inventory_items'
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('tc_players.id'), nullable=False)
    item_id = Column(Integer, ForeignKey('tc_items.id'), nullable=False)
    item = relationship("Item")

class Player(Base):
    __tablename__ = 'tc_players'
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    password = Column(String(64), nullable=False)
    timestamp = Column(DateTime)
    
    level = Column(Integer)
    exp = Column(Integer)
    total_gold = Column(Integer)
    tokens = Column(Integer)
    inventory = relationship("InventoryItem")
    #perks

class Character(Base):
    __tablename__ = "tc_characters"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('tc_players.id'))
    player = relationship("Player", backref="characters")
    name = Column(String(64))
    dead = Column(Boolean)
    depth = Column(Integer)
    room_id = Column(Integer, ForeignKey('tc_rooms.id'))
    room = relationship(Room, backref="characters")
    room_state = Column(Enum("none", "success", "failure"), nullable=False)
    class_ = Column(Enum("wizard", "ranger", "barbarian", "rogue"))
    
    hp          = Column(Integer) 
    fighting    = Column(Integer)
    swaying     = Column(Integer)
    pathfinding = Column(Integer)
    scouting    = Column(Integer)
    first_aid   = Column(Integer)
    problem_solving = Column(Integer)
    brute_forcing = Column(Integer)

    # abilities
    ability_points = Column(Integer)
    
    gold = Column(Integer)
    
    def __str__(self):
        return "Character {} {} of player {}, depth {}, room {} in state {}".format(self.class_, self.name, self.player, self.depth, self.room, self.room_state)
    
    def begin_session(self, session):
        self.messages = []
        self.choices = []
        self.session = session
    
    def proceed(self):
        self.depth += 1
        self.room_state = "none"
        self.messages.append("You've entered a new room.")
        rooms = self.session.query(Room).all()
        self.room = random.choice(rooms)
        self.room.begin_session(self) #eww?  or maybe this is right
        self.room.enter()

if __name__ == "__main__":
    Session = sessionmaker(bind=engine)#scoped_session(sessionmaker(bind=engine))
    session = Session()
    Base.metadata.drop_all(engine) 
    Base.metadata.create_all(engine) 

    items = [
        Item(name="Debug Staff", desc="May <s>explode</s>throw an exception at any moment.", category="equip", questable=False, effect="none", parameter={}),
        Item(name="Plain Staff", desc="Kind of shitty.", category="equip", questable=True, effect="passive", parameter={'effect': {'fighting': 1}}),
        Item(name="Rock", desc="Is nothing but extra weight.", category="trash", questable=True, effect="none", parameter={})
    ]

    for item in items:
        session.add(item)

    rooms = [
        PuzzleDoorRoom(problem_solving=5, brute_forcing=1, pathfinding=1, damage=20, door="wooden"),
        TreasureRoom(gold=20)
#        Room(type="treasure_room", parameter={})
    ]

    for room in rooms:
        session.add(room)
    
    foreveralone = Player(name="foreveralone", password="", timestamp=now(), level=1, exp=0, total_gold=20, tokens=5,
        inventory = [InventoryItem(item=items[1]), InventoryItem(item=items[2])])
    session.add(foreveralone)
    
    character = Character(player=foreveralone, name="Ofdslafd", dead=False, depth=1, class_="wizard",
        hp=60, fighting=1, swaying=1, pathfinding=1, scouting=1, first_aid=1, problem_solving=1, brute_forcing=1,
        ability_points=1, gold=5, room=rooms[0], room_state="none")
    
    session.add(character)
    
    session.commit()







