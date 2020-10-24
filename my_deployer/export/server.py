from bottle import route, run, response, request
from json import dumps
import docker

client = docker.from_env()

@route('/', ['OPTIONS', 'GET'])
def base():
    response.content_type = 'application/json'
    return dumps({"alive": True})

@route('/containers/', ['OPTIONS', 'GET'])
@route('/containers/<id>', ['OPTIONS', 'GET'])
def base(id = None):
    response.content_type = 'application/json'
    if id is None:
        a = False
        if 'all' in request.query:
            a = True
        cs = [{"name": c.name, "id":c.id} for c in client.containers.list(all=a)]
        return dumps({"containers": cs})
    try:
        c = client.containers.get(id)
    except:
        return {}
    if 'all' in request.query:
        d = c.attrs
    else:
        d = {
            "name": c.name,
            "short hash": c.short_id,
            "image": c.image.tags[0],
            "port": c.ports,
            "created": c.attrs['Created'],
            "volumes": c.attrs['Mounts']
        }
    return dumps({"id":d})

if __name__ == '__main__':
    run(host='0.0.0.0', port=80)
