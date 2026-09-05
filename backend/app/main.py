from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.routers.ships import router as ships_router
from backend.app.routers.events import router as events_router
from backend.app.routers.simulation import router as simulation_router
from backend.app.routers.ais import router as ais_router

app = FastAPI()
#添加中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174",],    #vue的来源
    allow_methods=["GET"],                      #请求方法
    allow_headers=["*"],                        #请求头
)

app.include_router(ships_router)    #把ships.py中定义的路由加入主应用
app.include_router(events_router)   #把events.py中定义的路由加入主应用
app.include_router(simulation_router)
app.include_router(ais_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
