from wsgiref.simple_server import make_server
from pyramid.config import Configurator
from pyramid.response import Response

from sql import *

from sqlalchemy import engine_from_config
from sqlalchemy.orm import sessionmaker
from pyramid.request import Request
from pyramid.decorator import reify

class MyRequest(Request):
    @reify
    def db(self):
        maker = self.registry.settings['db.sessionmaker']
        return maker()

def index(request):
    with open("index.html") as f:
        a = f.read()
    return Response(a)
    
def status(request):
    try:
        session = request.db

        player = session.query(Player).filter_by(id=1).one()
        character = player.characters[-1]
        character.begin_session(session) # XXX Is this really a good way? XXX eww passing the session
        room = character.room


        room.begin_session(character)
        
        messages = character.messages
        choices = character.choices
        
        log.info(character)
        
        if "action" in request.GET:
            action = request.GET['action']
            if action == "proceed" and character.room_state in ("success", "failure"):
                character.proceed()
            elif action == "escape":
                character.messages.append("Not implemented.  Restarted depth and healed.")
                character.depth = 1
                character.hp = 100
            elif character.room_state == "none":
                room.action(action)
        else:
            #messages.append("Nothing has changed.")
            room.enter()
        
        if "debug" in request.GET: # XXX change this to POST sometime
            debug = request.GET['debug']
            if debug == "increase_level":
                player.level += 1
                messages.append("DEBUG: You've gained a level!")
            elif debug == "give_item":
                item = session.query(Item).filter_by(id=1).one()
                player.inventory.items.append(InventoryItem(item=item))
                messages.append("DEBUG: You've got an item!")
        
        if character.room_state in ("success", "failure"):
            choices = ["proceed"] # XXX
        choices.append("escape")
        
        session.commit()
        
        json_inventory = []
        for inventory_item in player.inventory.items:
            item = inventory_item.item
            json_inventory.append({"name": item.name, "desc": item.desc, "category": item.category})
            
        sprite = None # TODO make this flexible
        if character.room.discriminator == "monster_room": # use character not room because room could've changed XXX
            sprite = character.room.creature.sprite
            
        s = {
            "game": {
                "player": {
                    "name": player.name,
                    "level": player.level,
                    "exp": player.exp,
                    "total_gold": player.total_gold,
                    "tokens": player.tokens,
                    "inventory": json_inventory
                },
                "character": {
                    "name": character.name,
                    "dead": character.dead,
                    "depth": character.depth,
                    "class": character.class_,
                    "hp": character.hp,
                    "skills": {
                        "Fighting": character.fighting,
                        "Swaying": character.swaying,
                        "Pathfinding": character.pathfinding,
                        "Scouting": character.scouting,
                        "First aid": character.first_aid,
                        "Problem solving": character.problem_solving,
                        "Brute forcing": character.brute_forcing
                    },
                    "ability_points": character.ability_points,
                    "gold": character.gold
                },
                "room": {
                    "type": character.room.discriminator,
                    "choices": choices,
                    "sprite": sprite
                },
                "console": messages
            },
            "chat": []
        }
        return Response(json.dumps(s))
    except Exception as ex:
        s = {
            "error": str(ex)
        }
        return Response(json.dumps(s))
        raise

if __name__ == '__main__':
    settings = {}
    
    maker = sessionmaker(bind=engine)
    settings['db.sessionmaker'] = maker

    config = Configurator(settings=settings, request_factory=MyRequest)

    config.add_route('index', '/')
    config.add_view(index, route_name='index')
    config.add_route('status', '/status')
    config.add_view(status, route_name='status')

    app = config.make_wsgi_app()
    server = make_server('0.0.0.0', 5223, app)
    print("Serving.")
    server.serve_forever()
