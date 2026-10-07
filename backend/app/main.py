from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid
from backend.app.routers.ships import router as ships_router
from backend.app.routers.events import router as events_router
from backend.app.routers.simulation import router as simulation_router
from backend.app.routers.mobility import router as mobility_router
from backend.app.routers.agent import router as agent_router
from backend.app.routers.tracks import router as tracks_router
from backend.app.routers.event_links import router as event_links_router
from backend.app.routers.dwell import router as dwell_router
from backend.app.routers.encounters import router as encounters_router
from backend.app.routers.data_health import router as data_health_router
from backend.app.routers.cases import router as cases_router
from backend.app.routers.area_activity import router as area_activity_router

app = FastAPI()
#添加中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://localhost:5176"],
    allow_methods=["GET", "POST"],               #请求方法
    allow_headers=["*"],                        #请求头
)

#请求参数校验失败的统一错误体（对齐智能体契约 detail{code,message,request_id}）
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "INVALID_REQUEST",
                "message": f"请求参数不合法：{exc.errors()[0]['msg'] if exc.errors() else '未知错误'}",
                "request_id": str(uuid.uuid4()),
            }
        },
    )

app.include_router(ships_router)    #把ships.py中定义的路由加入主应用
app.include_router(events_router)   #把events.py中定义的路由加入主应用
app.include_router(simulation_router)
app.include_router(mobility_router)
app.include_router(agent_router)
app.include_router(tracks_router)
app.include_router(event_links_router)
app.include_router(dwell_router)
app.include_router(encounters_router)
app.include_router(data_health_router)
app.include_router(cases_router)
app.include_router(area_activity_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
