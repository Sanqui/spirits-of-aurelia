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
    sprite = Column(String(255))
    category = Column(Enum("unspecified", "equip", "usable", "trash"), nullable=False)
    questable = Column(Boolean, nullable=False)
    effect = Column(Enum("none", "passive", "permanent"), nullable=False, default="none")
    parameter = Column(JSONEncodedDict, nullable=False)

class Creature(Base):
    __tablename__ = "tc_creatures"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    sprite = Column(String(255))
    type = Column(String(64), nullable=False) #make a table of this later
    beast = Column(Boolean, nullable=False)
    
    fighting = Column(Integer)
    swaying = Column(Integer)

class Room(Base):
    __tablename__ = "tc_rooms"
    id = Column(Integer, primary_key=True)
    min_depth= Column(Integer)
    max_depth= Column(Integer)
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
        f = getattr(self, "action_"+choice, None)
        if f is None:
            raise ValueError("Invalid choice for this type of room.")
        else:
            f()
        
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
        
    def enter(self):
        self.character.messages.append("You're in a puzzle door room.  [problem_solving = {}]".format(self.problem_solving))
        self.character.choices += ["solve", "force", "safe_path"]
        
    def failure(self, message=None):
        message += "  You took {} damage!".format(self.damage)
        if message: self.character.messages.append(message)
        self.character.room_state = "failure"
        self.character.choices = []
        self.character.hurt(self.damage)
        
    def action_solve(self):
        if self.character.problem_solving >= self.problem_solving:
            self.success("You've solved the door!")
        else:
            self.failure("Failed to solve the door!")
    
    def action_force(self):
        if self.character.brute_forcing >= self.brute_forcing:
            self.success("You've solved the door by brute forcing!")
        else:
            self.failure("Failed to brute force!")
    
    def action_safe_path(self):
        if self.character.pathfinding >= self.pathfinding:
            self.success("You've found a way to get past the door!")
        else:
            self.failure("Failed!")
            
class TreasureRoom(Room):
    __tablename__ = "tc_rooms_treasure_rooms"
    __mapper_args__ = {'polymorphic_identity': 'treasure_room'}
    id = Column(Integer, ForeignKey('tc_rooms.id'), primary_key=True)
    
    gold = Column(Integer)

    def enter(self):
        gold = self.gold
        if self.gold == None:
            gold = self.character.depth*99
        self.character.messages.append("You're in a treasure room.  There is {} gold.".format(gold))
        self.character.choices += ["pick_up"]
    
    def action_pick_up(self):
        gold = self.gold
        if self.gold == None:
            gold = self.character.depth*99
        self.character.gold += gold
        self.success("You've picked up the gold!")

class TrapRoom(Room):
    __tablename__ = "tc_rooms_trap_rooms"
    __mapper_args__ = {'polymorphic_identity': 'trap_room'}
    id = Column(Integer, ForeignKey('tc_rooms.id'), primary_key=True)
    
    damage = Column(Integer)

    def enter(self):
        if self.character.pathfinding > 3:
            self.character.messages.append("You have avoided an obvious trap room.")
            self.character.proceed(increase_depth=False)
        else:
            self.character.messages.append("It's a trap!")
            self.character.choices += ["run_through"]
        
    def action_run_through(self):
        self.character.hurt(self.damage)
        self.character.messages.append("You ran through the trap, taking {} damage!".format(self.damage))
        self.character.proceed()

class MonsterRoom(Room):
    __tablename__ = "tc_rooms_monster_rooms"
    __mapper_args__ = {'polymorphic_identity': 'monster_room'}
    id = Column(Integer, ForeignKey('tc_rooms.id'), primary_key=True)
    
    creature_id = Column(Integer, ForeignKey('tc_creatures.id'))
    creature = relationship("Creature")
        
    def enter(self):
        self.character.messages.append("You're in a monster room.  There is a {} in your way.".format(self.creature.name))
        self.character.choices += ["fight", "sway"]
        
    def success(self, message):
        gold = self.creature.swaying*20
        self.character.gold += gold
        message += "  You have gained {} gold!".format(gold)
        self.character.messages.append(message)
        self.character.room_state = "success"
        
    def failure(self, message):
        damage = self.creature.fighting*(19-self.creature.fighting)
        message += "  You took {} damage!".format(damage)
        self.character.hurt(damage)
        self.character.messages.append(message)
        self.character.room_state = "failure"
        
    def action_fight(self):
        if self.creature.fighting <= self.character.fighting:
            damage = self.creature.fighting*2
            self.character.hurt(damage)
            self.success("You have beaten {} losing {} HP.".format(self.creature.name, damage))
        else:
            self.failure("{} has beaten you up...".format(self.creature.name))

    def action_sway(self):
        if self.creature.swaying <= self.character.swaying:
            self.success("You've swayed past {}!".format(self.creature.name))
        else:
            self.failure("You failed to sway past {}...".format(self.creature.name))

class GuardianRoom(Room):
    __tablename__ = "tc_rooms_guardian_rooms"
    __mapper_args__ = {'polymorphic_identity': 'guardian_room'}
    id = Column(Integer, ForeignKey('tc_rooms.id'), primary_key=True)
    
    creature_id = Column(Integer, ForeignKey('tc_creatures.id'))
    creature = relationship("Creature")
        
    def enter(self):
        self.character.messages.append("You're in a guardian room.  There is a {} guarding some treasure!".format(self.creature.name))
        self.character.choices += ["ignore", "fight", "sway"]
        
    def success(self, message):
        gold = self.character.depth*99
        self.character.gold += gold
        message += "  You have gained {} gold!".format(gold)
        self.character.messages.append(message)
        self.character.room_state = "success"
        
    def failure(self, message):
        damage = self.creature.fighting*(19-self.creature.fighting)
        message += "  You took {} damage!".format(damage)
        self.character.hurt(damage)
        self.character.messages.append(message)
        self.character.room_state = "failure"
    
    def choice_ignore(self):
        self.character.messages.append("You silently walked towards the door.")
        self.character.proceed()
    
    def choice_fight(self):
        if self.creature.fighting <= self.character.fighting:
            damage = self.creature.fighting*2
            self.character.hurt(damage)
            self.success("You have beaten {} losing {} HP.".format(self.creature.name, damage))
        else:
            self.failure("{} has beaten you up...".format(self.creature.name))
    
    def choice_sway(self):
        if self.creature.swaying <= self.character.swaying:
            self.success("You've swayed past {}!".format(self.creature.name))
        else:
            self.failure("You failed to sway past {}...".format(self.creature.name))
            
class InventoryItem(Base):
    __tablename__ = 'tc_inventory_items'
    id = Column(Integer, primary_key=True)
    inventory_id = Column(Integer, ForeignKey('tc_inventories.id'), nullable=False)
    inventory = relationship("Inventory", backref="items")
    item_id = Column(Integer, ForeignKey('tc_items.id'), nullable=False)
    item = relationship("Item")

class Inventory(Base):
    __tablename__ = "tc_inventories"
    id = Column(Integer, primary_key=True)
    size = Column(Integer)

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
    inventory_id = Column(Integer, ForeignKey('tc_inventories.id'), nullable=False)
    inventory = relationship("Inventory", backref="owner")
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
    
    def proceed(self, increase_depth=True):
        if increase_depth:
            self.depth += 1
        self.room_state = "none"
        self.messages.append("You've entered a new room.")
        rooms = self.session.query(Room).all()
        self.room = random.choice(rooms)
        self.room.begin_session(self) #eww?  or maybe this is right
        self.room.enter()

    def hurt(self, damage, message=None):
        self.hp -= damage
        if message:
            self.messages.append(message.format(damage=damage))
        if self.hp <= 0:
            self.messages.append("You have died.")
            self.depth = 0
            self.proceed()
            self.hp = 100 # TODO
        
    def heal(self, heal, message=None):
        if message: self.messages.append(message.format(heal))
        if self.hp == 100:
            self.messages.append("But it had no effect!")
        else:
            self.hp += heal
            if self.hp > 100:
                self.hp = 100
        
if __name__ == "__main__":
    Session = sessionmaker(bind=engine)#scoped_session(sessionmaker(bind=engine))
    session = Session()
    Base.metadata.drop_all(engine) 
    Base.metadata.create_all(engine) 

    items = [
        Item(name="Debug Staff", desc="May <s>explode</s>throw an exception at any moment.", category="equip", questable=False, effect="none", parameter={}),
        Item(name="Plain Staff", desc="Kind of shitty.", category="equip", questable=True, effect="passive", parameter={'effect': {'fighting': 1}}),
        Item(name="Rock", desc="Is nothing but extra weight.", category="trash", questable=True, effect="none", parameter={}),
        Item(name="Book", sprite="items/book.png", desc="Eggs on back, what's inside?", category="trash", questable=True, effect="none", parameter={}),
        Item(name="Potion", sprite="items/potion.png", desc="Heals you, I guess.", category="usable", questable=True, effect="permanent", parameter={'effect': {'hp': 20}}),
        Item(name="Sword", sprite="items/sword.png", desc="A sword.  What's there to say?", category="equip", questable=True, effect="passive", parameter={'effect': {'fighting': 1}})
    ]

    for item in items:
        session.add(item)
    
    creatures = [
        Creature(name="Rat", sprite="http://www.zabij10prasat.cz/kusaba/z10p/src/133261904284.png", type="rat", beast=False, fighting=1, swaying=3),
        Creature(name="Bear", sprite="http://www.zabij10prasat.cz/kusaba/z10p/src/133267590222.png", type="bear", beast=True, fighting=5, swaying=1),
        Creature(name="Pony", sprite="http://www.zabij10prasat.cz/kusaba/z10p/src/133390050052.png", type="pony", beast=True, fighting=5, swaying=5),
        Creature(name="Ponyta", sprite="http://www.zabij10prasat.cz/kusaba/z10p/src/133390054533.png", type="pony", beast=True, fighting=20, swaying=20)
        ]
    for creature in creatures:
        session.add(creature)
    
    rooms = [
        PuzzleDoorRoom(min_depth=1, max_depth=None, problem_solving=5, brute_forcing=1, pathfinding=1, damage=20, door="wooden"),
        TreasureRoom(min_depth=1, max_depth=None, gold=None),
        MonsterRoom(min_depth=1, max_depth=None, creature=creatures[0]),
        MonsterRoom(min_depth=1, max_depth=None, creature=creatures[1]),
        TrapRoom(min_depth=2, max_depth=None, damage=20),
        GuardianRoom(min_depth=1, max_depth=None, creature=creatures[3]),
    ]

    for room in rooms:
        session.add(room)
    
    foreveralone = Player(name="foreveralone", password="", timestamp=now(), level=1, exp=0, total_gold=20, tokens=5,
        inventory = Inventory(items=[InventoryItem(item=items[3]), InventoryItem(item=items[4]), InventoryItem(item=items[5])], size=9))
    session.add(foreveralone)
    
    character = Character(player=foreveralone, name="Ofdslafd", dead=False, depth=1, class_="wizard",
        hp=60, fighting=1, swaying=1, pathfinding=1, scouting=1, first_aid=1, problem_solving=1, brute_forcing=1,
        ability_points=1, gold=5, room=rooms[0], room_state="none")
    
    session.add(character)
    
    session.commit()







