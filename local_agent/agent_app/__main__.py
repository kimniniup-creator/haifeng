import uvicorn
from .config import Config

if __name__ == '__main__':
    config = Config()
    uvicorn.run('agent_app.main:app',host=config.agent_host,port=config.port,workers=1)
