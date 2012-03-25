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
        print(self.registry.settings)
        maker = self.registry.settings['db.sessionmaker']
        return maker()

def index(request):
    with open("index.html") as f:
        a = f.read()
    return Response(a)
    
def status(request):
    session = request.db

    player = session.query(Player).filter_by(id=1).one()
    player.__init__() # Is this really a good way?
    character = player.characters[-1]
    room = character.room
    
    messages = player.messages
    
    something_happened = False
    
    if "action" in request.GET:
        action = request.GET['action']
    else:
        messages.append("Nothing has changed.")
    
    if "debug" in request.GET: # XXX change this to POST sometime
        debug = request.GET['debug']
        if debug == "increase_level":
            player.level += 1
            messages.append("DEBUG: You've gained a level!")
        elif debug == "give_item":
            item = session.query(Item).filter_by(id=1).one()
            player.inventory.append(InventoryItem(item=item))
            messages.append("DEBUG: You've got an item!")
        session.commit()
    
    inventory = []
    for inventory_item in player.inventory:
        item = inventory_item.item
        inventory.append({"name": item.name, "desc": item.desc, "category": item.category})
    s = {
        "game": {
            "player": {
                "name": player.name,
                "level": player.level,
                "exp": player.exp,
                "total_gold": player.total_gold,
                "tokens": player.tokens,
                "inventory": inventory
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
                "type": room.type,
                "choices": {
                    "solve": "Solve",
                    "use_force": "Use force",
                    "safe_path": "Find a safe path"
                }
            },
            "console": messages
        },
        "chat": []
    }
    return Response(json.dumps(s))

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
    server = make_server('0.0.0.0', 8088, app)
    print("Serving.")
    server.serve_forever()
