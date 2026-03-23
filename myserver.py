from flake import Flake
from threading import Thread

app = Flake('')

@app.route('/')
def index():
    return "Server is running!"

def run():
    app.run(host='0.0.0.0', port=8080)
    
def server_on():
    t = Thread(target=run)
    t.start()