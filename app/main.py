from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os
from .database import engine, Base
from .routers import auth, users, rooms

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bowling Manager API")

# Setup templates and static
current_dir = os.path.dirname(os.path.realpath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(current_dir, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(current_dir, "templates"))

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(rooms.router)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")

@app.get("/forgot-password", response_class=HTMLResponse)
async def get_forgot_password(request: Request):
    return templates.TemplateResponse(request=request, name="forgot_password.html")

@app.get("/reset-password", response_class=HTMLResponse)
async def get_reset_password(request: Request):
    return templates.TemplateResponse(request=request, name="reset_password.html")

@app.get("/profile", response_class=HTMLResponse)
async def get_profile(request: Request):
    return templates.TemplateResponse(request=request, name="profile.html")

@app.get("/rooms", response_class=HTMLResponse)
async def get_rooms(request: Request):
    return templates.TemplateResponse(request=request, name="rooms.html")

@app.get("/rooms/{room_id}", response_class=HTMLResponse)
async def get_room_detail(request: Request, room_id: int):
    return templates.TemplateResponse(request=request, name="room_detail.html", context={"room_id": room_id})

@app.get("/rooms/{room_id}/games/new", response_class=HTMLResponse)
async def get_new_game(request: Request, room_id: int):
    return templates.TemplateResponse(request=request, name="game_new.html", context={"room_id": room_id})
