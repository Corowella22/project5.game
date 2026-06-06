import pygame
import math
import random
import array
import socket
import threading
import json
import os
import time
from dataclasses import dataclass
from typing import List
from collections import defaultdict

pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=16, buffer=512)

info = pygame.display.Info()
MAX_WIDTH, MAX_HEIGHT = info.current_w, info.current_h
WIDTH, HEIGHT = 800, 600

screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE | pygame.HWSURFACE | pygame.DOUBLEBUF)
pygame.display.set_caption("TERRY SURVIVAL - MULTIPLAYER")
clock = pygame.time.Clock()

#звуки
def make_sound(wave_func, duration, vol=0.1, fade_out=True):
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    buf = array.array('h')
    for i in range(n_samples):
        t = i / sample_rate
        sample = wave_func(t) * 32767 * vol
        if fade_out: sample *= (1.0 - (i / n_samples))
        buf.append(int(max(-32768, min(32767, sample))))
    return pygame.mixer.Sound(buffer=buf.tobytes())

snd_swing = make_sound(lambda t: math.sin(2 * math.pi * (600 - t*2000) * t), 0.15, 0.1)
snd_hit = make_sound(lambda t: random.uniform(-1, 1) * math.sin(2 * math.pi * 80 * t), 0.2, 0.4)
snd_chop = make_sound(lambda t: random.uniform(-1, 1), 0.1, 0.2)
snd_wolf_die = make_sound(lambda t: 1.0 if (t * (150 - t*300)) % 1.0 > 0.5 else -1.0, 0.4, 0.2)
snd_berry = make_sound(lambda t: math.sin(2 * math.pi * 800 * t), 0.05, 0.1)
snd_wolf_bite = make_sound(lambda t: math.sin(2 * math.pi * 150 * t) * (1 - t*3) + random.uniform(-0.5, 0.5), 0.3, 0.5)
snd_bgm = make_sound(lambda t: math.sin(2 * math.pi * 55 * t) * 0.5 + math.sin(2 * math.pi * 56.5 * t) * 0.5, 2.0, 0.15, False)
snd_bgm.play(loops=-1)

snd_rain = make_sound(lambda t: random.uniform(-0.1, 0.1), 1.0, 1.0, False)
RAIN_CHANNEL = pygame.mixer.Channel(6)

if os.path.exists("sound.mp3"): snd_cave = pygame.mixer.Sound("sound.mp3")
else: snd_cave = make_sound(lambda t: math.sin(2*math.pi*45*t) * (0.5 + 0.5*math.sin(t*2)) + random.uniform(-0.1, 0.1), 3.0, 0.5, False)
CAVE_CHANNEL = pygame.mixer.Channel(5)


BLACK, WHITE = (0, 0, 0), (250, 250, 255)
GREEN, BRIGHT_GREEN = (20, 170, 20), (100, 255, 100)
CYAN, BRIGHT_CYAN = (0, 180, 180), (85, 255, 255)
RED, BRIGHT_RED = (180, 0, 0), (255, 85, 85)
BROWN = (130, 80, 40)
LIGHT_GRAY, DARK_GRAY = (150, 150, 150), (90, 90, 90)
BRIGHT_BLUE = (85, 100, 255)
YELLOW = (255, 255, 100)

@dataclass
class Vector3:
    x: float; y: float; z: float
    def __add__(self, other): return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)
    def __sub__(self, other): return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)
    def __mul__(self, scalar): return Vector3(self.x * scalar, self.y * scalar, self.z * scalar)
    def length(self): return math.sqrt(self.x**2 + self.y**2 + self.z**2)
    def normalize(self):
        l = self.length()
        return Vector3(self.x/l, self.y/l, self.z/l) if l > 0 else Vector3(0, 0, 0)
    def dot(self, other): return self.x * other.x + self.y * other.y + self.z * other.z

class Face:
    __slots__ = ['vertices', 'color', 'distance', 'center', 'normal']
    def __init__(self, vertices: List[Vector3], color):
        self.vertices, self.color, self.distance, self.center, self.normal = vertices, color, 0, None, None
    def get_center(self):
        if self.center is None:
            self.center = Vector3(sum(v.x for v in self.vertices)/len(self.vertices), sum(v.y for v in self.vertices)/len(self.vertices), sum(v.z for v in self.vertices)/len(self.vertices))
        return self.center
    def get_normal(self):
        if self.normal is None:
            if len(self.vertices) < 3: self.normal = Vector3(0, 1, 0)
            else:
                v1, v2 = self.vertices[1] - self.vertices[0], self.vertices[2] - self.vertices[0]
                self.normal = Vector3(v1.y*v2.z - v1.z*v2.y, v1.z*v2.x - v1.x*v2.z, v1.x*v2.y - v1.y*v2.x).normalize()
        return self.normal

class Star:
    def __init__(self):
        dist = 300
        theta = random.uniform(0, 2*math.pi)
        phi = random.uniform(0.1, math.pi/2)
        self.offset = Vector3(dist * math.cos(theta) * math.cos(phi), dist * math.sin(phi), dist * math.sin(theta) * math.cos(phi))
        c = random.randint(150, 255)
        self.color = (c, c, c)

class Puddle:
    def __init__(self, x, z, y):
        self.pos = Vector3(x, y + 0.05, z)
        self.max_size = random.uniform(0.8, 2.5)
        self.size = self.max_size
        self.wetness = 100.0
        self.faces_cache = None
    def get_or_create_faces(self, renderer):
        if self.faces_cache is None:
            s = self.size / 2
            v1, v2, v3, v4 = Vector3(self.pos.x - s, self.pos.y, self.pos.z - s), Vector3(self.pos.x + s, self.pos.y, self.pos.z - s), Vector3(self.pos.x + s, self.pos.y, self.pos.z + s), Vector3(self.pos.x - s, self.pos.y, self.pos.z + s)
            self.faces_cache = Face([v1, v2, v3, v4], (80, 130, 180))
        return [self.faces_cache]

class NetworkManager:
    DEFAULT_SERVER = '127.0.0.1' 
    DEFAULT_PORT = 6767
    
    def __init__(self, host=None, port=None):
        self.host = host or self.DEFAULT_SERVER
        self.port = port or self.DEFAULT_PORT
        self.sock, self.connected = None, False
        self.player_id, self.terrain_seed = None, None
        self.other_players, self.network_wolves = {}, []
        self.chopped_trees, self.collected_berries = set(), set()
        self.day_time, self.days_survived = 0, 1
        self.spawn_x, self.spawn_z = 0, 0
        self.chat_messages = []
        
    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(3.0)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(None)
            self.connected = True
            init_data = self.recv_json()
            if init_data and init_data['type'] == 'init':
                self.player_id, self.terrain_seed = init_data['player_id'], init_data['terrain_seed']
                self.spawn_x, self.spawn_z = init_data['spawn_x'], init_data['spawn_z']
                self.day_time, self.days_survived = init_data.get('day_time', 0), init_data.get('days_survived', 1)
                return True
            return False
        except Exception as e:
            print("Не удалось подключиться к серверу:", e)
            self.connected = False; return False
    
    def send_position(self, x, y, z, angle, pitch):
        if self.connected: self.send_json({'type': 'update_position', 'x': x, 'y': y, 'z': z, 'angle': angle, 'pitch': pitch})
    
    def send_stats(self, health, hunger, wood, berries):
        if self.connected: self.send_json({'type': 'update_stats', 'health': health, 'hunger': hunger, 'wood': wood, 'berries': berries})
    
    def send_chop_tree(self, x, z):
        if self.connected: self.send_json({'type': 'chop_tree', 'x': x, 'z': z})
    
    def send_collect_berry(self, x, z):
        if self.connected: self.send_json({'type': 'collect_berry', 'x': x, 'z': z})
    
    def send_attack_wolf(self, wolf_id, damage):
        if self.connected: self.send_json({'type': 'attack_wolf', 'wolf_id': wolf_id, 'damage': damage})
        
    def send_chat(self, msg):
        if self.connected: self.send_json({'type': 'chat', 'msg': msg})
    
    def receive_loop(self):
        while self.connected:
            try:
                data = self.recv_json()
                if not data: break
                if data['type'] == 'game_state':
                    self.other_players = {p['id']: p for p in data['players'] if p['id'] != self.player_id}
                    self.network_wolves = data['wolves']
                    self.chopped_trees = set(tuple(t) for t in data['chopped_trees'])
                    self.collected_berries = set(tuple(b) for b in data['collected_berries'])
                    self.day_time, self.days_survived = data['day_time'], data['days_survived']
                elif data['type'] == 'chat':
                    self.chat_messages.append({'name': data['name'], 'msg': data['msg']})
                    if len(self.chat_messages) > 10: self.chat_messages.pop(0)
            except: break
        self.connected = False
    
    def send_json(self, data):
        if not self.sock: return
        try:
            msg = json.dumps(data).encode('utf-8')
            self.sock.sendall(len(msg).to_bytes(4, byteorder='big'))
            self.sock.sendall(msg)
        except: self.connected = False
    
    def recv_json(self):
        if not self.sock: return None
        try:
            lb = self.sock.recv(4)
            if not lb: return None
            l = int.from_bytes(lb, byteorder='big')
            chunks, rec = [], 0
            while rec < l:
                chunk = self.sock.recv(min(l - rec, 4096))
                if not chunk: return None
                chunks.append(chunk); rec += len(chunk)
            return json.loads(b''.join(chunks).decode('utf-8'))
        except: return None
    
    def disconnect(self):
        self.connected = False
        if self.sock:
            try: self.sock.close()
            except: pass

class Player:
    def __init__(self):
        self.pos = Vector3(0, 1.6, 0)
        self.velocity, self.angle, self.pitch = Vector3(0, 0, 0), 0, 0
        self.health, self.hunger = 100.0, 100.0
        self.wood, self.berries = 0, 0
        self.spear_equipped, self.attack_timer, self.collision_radius = False, 0.0, 0.4
        self.is_grounded = True 

class OtherPlayer:
    def __init__(self, pid, name):
        self.id, self.name = pid, name
        self.pos, self.angle, self.pitch, self.health = Vector3(0, 1.6, 0), 0, 0, 100
    def get_or_create_faces(self, renderer):
        body_pos = Vector3(self.pos.x, self.pos.y - 0.3, self.pos.z)
        f = renderer.create_cube(body_pos, 0.8, BRIGHT_BLUE)
        f += renderer.create_cube(Vector3(self.pos.x + math.cos(self.angle)*0.3, self.pos.y + 0.5, self.pos.z + math.sin(self.angle)*0.3), 0.5, BRIGHT_CYAN)
        return f

class Tree:
    def __init__(self, x, z, ground_y, rng):
        self.pos = Vector3(x, ground_y, z)
        self.height, self.trunk_radius, self.crown_radius = rng.uniform(4, 8), rng.uniform(0.2, 0.4), rng.uniform(1.8, 3.0)
        self.leaves_color = (0, rng.randint(140, 240), 0)
        self.chopped, self.faces_cache, self.chopped_cache, self.collision_radius = False, None, None, self.trunk_radius + 0.3
    def get_or_create_faces(self, renderer):
        if self.chopped:
            if self.chopped_cache is None: self.chopped_cache = renderer.create_cylinder(self.pos, 0.5, self.trunk_radius, BROWN, 5)
            return self.chopped_cache
        if self.faces_cache is None:
            self.faces_cache = renderer.create_cylinder(self.pos, self.height * 0.6, self.trunk_radius, BROWN, 5) + renderer.create_cone(Vector3(self.pos.x, self.pos.y + self.height * 0.5, self.pos.z), self.height * 0.5, self.crown_radius, self.leaves_color, 6)
        return self.faces_cache

class Rock:
    def __init__(self, x, z, ground_y, rng, scale=1.0):
        self.pos, self.size = Vector3(x, ground_y, z), rng.uniform(0.6, 1.5) * scale
        self.color, self.faces_cache = (rng.randint(80,130),)*3, None
    def get_or_create_faces(self, renderer):
        if self.faces_cache is None: self.faces_cache = renderer.create_cone(self.pos, self.size, self.size * 0.8, self.color, seg=5)
        return self.faces_cache

class Berry:
    def __init__(self, x, z, ground_y, rng):
        self.pos, self.collected, self.faces_cache = Vector3(x, ground_y + 0.3, z), False, None
    def get_or_create_faces(self, renderer):
        if self.collected: return []
        if self.faces_cache is None: self.faces_cache = renderer.create_cube(self.pos, 0.4, RED)
        return self.faces_cache

class WolfBase:
    def get_or_create_faces(self, renderer):
        if not self.alive: return []
        bob = abs(math.sin(self.walk_phase)) * 0.15
        f = renderer.create_cube(Vector3(self.pos.x, self.pos.y + 0.5 + bob, self.pos.z), 0.8, DARK_GRAY)
        f += renderer.create_cube(Vector3(self.pos.x + math.cos(self.angle)*0.6, self.pos.y + 0.6 + bob, self.pos.z + math.sin(self.angle)*0.6), 0.5, DARK_GRAY)
        f += renderer.create_cube(Vector3(self.pos.x + math.cos(self.angle)*0.7, self.pos.y + 0.7 + bob, self.pos.z + math.sin(self.angle)*0.7), 0.2, BRIGHT_RED)
        return f

class NetworkWolf(WolfBase):
    def __init__(self, wolf_id):
        self.id, self.pos, self.angle, self.walk_phase, self.health, self.alive = wolf_id, Vector3(0,0,0), 0, 0, 30, True
        self.attack_cooldown = 0.0 

class LocalWolf(WolfBase):
    def __init__(self, x, z):
        self.id = random.randint(1000, 9999)
        self.pos = Vector3(x, 0, z)
        self.angle = random.uniform(0, 2*math.pi)
        self.health, self.alive, self.walk_phase, self.attack_cooldown = 30, True, 0.0, 0.0

class Terrain:
    def __init__(self, seed=None):
        self.seed = seed if seed else random.randint(0, 10000)
        self.height_cache = {}
        random.seed(self.seed)
        self.noise_map = defaultdict(lambda: random.uniform(-1, 1))
        random.seed()

    def smooth_noise(self, x, z, scale, offset_layer=0):
        sx, sz = x * scale, z * scale
        x0, z0 = math.floor(sx), math.floor(sz)
        lx, lz = sx - x0, sz - z0
        lx = lx * lx * (3 - 2 * lx)
        lz = lz * lz * (3 - 2 * lz)
        n00, n10 = self.noise_map[(x0, z0, offset_layer)], self.noise_map[(x0+1, z0, offset_layer)]
        n01, n11 = self.noise_map[(x0, z0+1, offset_layer)], self.noise_map[(x0+1, z0+1, offset_layer)]
        return (n00 + lx*(n10-n00)) + lz*((n01 + lx*(n11-n01)) - (n00 + lx*(n10-n00)))

    def get_base_height(self, x, z):
        key = (math.floor(x*2), math.floor(z*2))
        if key in self.height_cache: return self.height_cache[key]
        h = self.smooth_noise(x, z, 0.05, 1) * 4 + self.smooth_noise(x, z, 0.1, 2) * 2
        mountain = self.smooth_noise(x, z, 0.01, 3)
        if mountain > 0.2: h += (mountain - 0.2) * 35 
        dx, dz = x - 150, z - 150
        dist = math.hypot(dx, dz)
        if dist < 120:
            if dist > 50: crater_h = (120 - dist) * 0.7 
            else: crater_h = -35 + (dist / 50.0) * 84 
            if dx < 0 and abs(dz) < 25:
                blend = max(0, 1.0 - abs(dz)/25.0)
                crater_h = crater_h * (1 - blend) + (h + 5) * blend
            h += crater_h
        self.height_cache[key] = h
        return h

    def get_exact_height(self, x, z):
        grid = 6
        x0, z0 = math.floor(x/grid)*grid, math.floor(z/grid)*grid
        lx, lz = (x - x0)/grid, (z - z0)/grid
        y00, y10 = self.get_base_height(x0, z0), self.get_base_height(x0+grid, z0)
        y01, y11 = self.get_base_height(x0, z0+grid), self.get_base_height(x0+grid, z0+grid)
        if lx >= lz: return y00 + lx*(y10-y00) + lz*(y11-y10)
        else: return y00 + lx*(y11-y01) + lz*(y01-y00)

class Chunk:
    def __init__(self, cx, cz, terrain):
        self.cx, self.cz, self.faces, self.trees, self.berries, self.rocks = cx, cz, [], [], [], []
        self.generate(terrain)

    def generate(self, terrain):
        grid_step = 6
        for x in range(6):
            for z in range(6):
                x1, z1 = self.cx * 36 + x * grid_step, self.cz * 36 + z * grid_step
                x2, z2 = x1 + grid_step, z1 + grid_step
                y1, y2 = terrain.get_base_height(x1, z1), terrain.get_base_height(x2, z1)
                y3, y4 = terrain.get_base_height(x2, z2), terrain.get_base_height(x1, z2)
                avg_y = (y1 + y2 + y3 + y4) / 4
                dist_to_cave = math.hypot(((x1+x2)/2) - 150, ((z1+z2)/2) - 150)
                
                if avg_y > 40: color = WHITE 
                elif dist_to_cave < 60 and avg_y < 10: color = (max(30, int(40 + avg_y*2)), max(30, int(40 + avg_y*2)), max(35, int(45 + avg_y*2)))
                elif avg_y > 12: color = DARK_GRAY 
                elif avg_y > 6: color = LIGHT_GRAY
                elif avg_y > 3: color = BROWN
                else: color = GREEN if (x + z) % 2 == 0 else (30, 160, 30)
                self.faces.append(Face([Vector3(x1,y1,z1), Vector3(x2,y2,z1), Vector3(x2,y3,z2)], color))
                self.faces.append(Face([Vector3(x1,y1,z1), Vector3(x2,y3,z2), Vector3(x1,y4,z2)], color))

        rng = random.Random(hash((self.cx, self.cz, terrain.seed)))
        dist_c = math.hypot(self.cx*36+18 - 150, self.cz*36+18 - 150)
        
        for _ in range(rng.randint(4, 8) if (self.cx != 0 or self.cz != 0) else 2):
            tx, tz = self.cx * 36 + rng.uniform(2, 34), self.cz * 36 + rng.uniform(2, 34)
            th = terrain.get_exact_height(tx, tz)
            if dist_c > 65: self.trees.append(Tree(tx, tz, th, rng))
        for _ in range(rng.randint(2, 5)):
            bx, bz = self.cx * 36 + rng.uniform(2, 34), self.cz * 36 + rng.uniform(2, 34)
            bh = terrain.get_exact_height(bx, bz)
            if dist_c > 65: self.berries.append(Berry(bx, bz, bh, rng))
        for _ in range(rng.randint(4, 10) if dist_c < 60 else rng.randint(1, 3)):
            rx, rz = self.cx * 36 + rng.uniform(2, 34), self.cz * 36 + rng.uniform(2, 34)
            self.rocks.append(Rock(rx, rz, terrain.get_exact_height(rx, rz), rng, rng.uniform(1.5, 3.0) if dist_c < 60 else 1.0))

class Renderer3D:
    def __init__(self, player):
        self.player = player
        self.near, self.far, self.fov = 0.1, 90, 400
        self.light_dir = Vector3(0.3, -1, 0.2).normalize()
        self.cx_min, self.cy_min, self.cx_max, self.cy_max = -50, -50, WIDTH+50, HEIGHT+50

    def transform_to_camera(self, point):
        dx, dy, dz = point.x - self.player.pos.x, point.y - self.player.pos.y, point.z - self.player.pos.z
        cos_y, sin_y = math.cos(-self.player.angle), math.sin(-self.player.angle)
        xr, zr = dx * cos_y - dz * sin_y, dx * sin_y + dz * cos_y
        cos_p, sin_p = math.cos(-self.player.pitch), math.sin(-self.player.pitch)
        return (xr, dy * cos_p - zr * sin_p, dy * sin_p + zr * cos_p)

    def clip_polygon_near(self, verts):
        if len(verts) < 3: return []
        out = []
        for i in range(len(verts)):
            c, nx = verts[i], verts[(i+1)%len(verts)]
            if c[2] >= self.near:
                out.append(c)
                if nx[2] < self.near: out.append((c[0] + (self.near-c[2])/(nx[2]-c[2])*(nx[0]-c[0]), c[1] + (self.near-c[2])/(nx[2]-c[2])*(nx[1]-c[1]), self.near))
            elif nx[2] >= self.near: out.append((c[0] + (self.near-c[2])/(nx[2]-c[2])*(nx[0]-c[0]), c[1] + (self.near-c[2])/(nx[2]-c[2])*(nx[1]-c[1]), self.near))
        return out

    def clip_polygon_2d(self, poly):
        def clip(p, inside, lerp):
            out = []
            for i in range(len(p)):
                c, nx = p[i], p[(i+1)%len(p)]
                if inside(c):
                    out.append(c)
                    if not inside(nx): out.append(lerp(c, nx))
                elif inside(nx): out.append(lerp(c, nx))
            return out
        poly = clip(poly, lambda p: p[0] >= self.cx_min, lambda a,b: (self.cx_min, a[1]+(self.cx_min-a[0])/(b[0]-a[0])*(b[1]-a[1]) if a[0]!=b[0] else a[1]))
        poly = clip(poly, lambda p: p[0] <= self.cx_max, lambda a,b: (self.cx_max, a[1]+(self.cx_max-a[0])/(b[0]-a[0])*(b[1]-a[1]) if a[0]!=b[0] else a[1]))
        poly = clip(poly, lambda p: p[1] >= self.cy_min, lambda a,b: (a[0]+(self.cy_min-a[1])/(b[1]-a[1])*(b[0]-a[0]) if a[1]!=b[1] else a[0], self.cy_min))
        poly = clip(poly, lambda p: p[1] <= self.cy_max, lambda a,b: (a[0]+(self.cy_max-a[1])/(b[1]-a[1])*(b[0]-a[0]) if a[1]!=b[1] else a[0], self.cy_max))
        return poly

    def create_cube(self, center, size, color):
        s = size / 2
        v = [Vector3(center.x-s, center.y-s, center.z-s), Vector3(center.x+s, center.y-s, center.z-s),
             Vector3(center.x+s, center.y+s, center.z-s), Vector3(center.x-s, center.y+s, center.z-s),
             Vector3(center.x-s, center.y-s, center.z+s), Vector3(center.x+s, center.y-s, center.z+s),
             Vector3(center.x+s, center.y+s, center.z+s), Vector3(center.x-s, center.y+s, center.z+s)]
        return [Face([v[0],v[1],v[2],v[3]], color), Face([v[5],v[4],v[7],v[6]], color),
                Face([v[4],v[0],v[3],v[7]], color), Face([v[1],v[5],v[6],v[2]], color),
                Face([v[3],v[2],v[6],v[7]], color), Face([v[4],v[5],v[1],v[0]], color)]

    def create_cylinder(self, b, h, r, col, seg=6):
        f = []
        for i in range(seg):
            a1, a2 = (i/seg)*2*math.pi, ((i+1)/seg)*2*math.pi
            f.append(Face([Vector3(b.x+math.cos(a1)*r,b.y,b.z+math.sin(a1)*r), Vector3(b.x+math.cos(a2)*r,b.y,b.z+math.sin(a2)*r), 
                           Vector3(b.x+math.cos(a2)*r,b.y+h,b.z+math.sin(a2)*r), Vector3(b.x+math.cos(a1)*r,b.y+h,b.z+math.sin(a1)*r)], col))
        return f

    def create_cone(self, b, h, r, col, seg=6):
        f, top = [], Vector3(b.x, b.y+h, b.z)
        for i in range(seg):
            a1, a2 = (i/seg)*2*math.pi, ((i+1)/seg)*2*math.pi
            f.append(Face([Vector3(b.x+math.cos(a1)*r,b.y,b.z+math.sin(a1)*r), Vector3(b.x+math.cos(a2)*r,b.y,b.z+math.sin(a2)*r), top], col))
        return f

    def draw_polygon(self, face, fog_color):
        cam = [self.transform_to_camera(v) for v in face.vertices]
        clipped = self.clip_polygon_near(cam)
        if len(clipped) < 3: return
        proj = []
        hw, hh = WIDTH/2, HEIGHT/2
        for x, y, z in clipped: proj.append((int(hw + (x*self.fov)/max(z, 1e-10)), int(hh - (y*self.fov)/max(z, 1e-10))))
        proj2d = self.clip_polygon_2d(proj)
        if len(proj2d) < 3: return
        area = sum(proj2d[i][0]*proj2d[(i+1)%len(proj2d)][1] - proj2d[(i+1)%len(proj2d)][0]*proj2d[i][1] for i in range(len(proj2d)))
        if area >= 0: return
        br = max(0.2, -face.get_normal().dot(self.light_dir))
        r, g, b = int(face.color[0]*br), int(face.color[1]*br), int(face.color[2]*br)
        fog_start, fog_end = self.far * 0.4, self.far * 0.95
        dist = face.distance
        if dist > fog_start:
            f = min(1.0, (dist - fog_start) / (fog_end - fog_start))
            r, g, b = int(r*(1-f) + fog_color[0]*f), int(g*(1-f) + fog_color[1]*f), int(b*(1-f) + fog_color[2]*f)
        try:
            pygame.draw.polygon(screen, (r,g,b), proj2d)
            if area < -100:
                if dist > fog_start: pygame.draw.polygon(screen, (int(fog_color[0]*f), int(fog_color[1]*f), int(fog_color[2]*f)), proj2d, 1)
                else: pygame.draw.polygon(screen, BLACK, proj2d, 1)
        except: pass

class Game:
    def __init__(self, multiplayer=True, server_ip=None):
        self.multiplayer = multiplayer
        self.network = NetworkManager(host=server_ip) if multiplayer else None
        
        self.cave_intensity, self.cave_sound_playing = 0.0, False
        self.chat_active, self.chat_input = False, ""
        self.is_raining, self.rain_intensity, self.rain_duration, self.rain_check_timer, self.rain_chance = False, 0.0, 0, 0, 0.3 
        self.puddles = []
        self.raindrops = [[random.uniform(-15, 15), random.uniform(-5, 20), random.uniform(-15, 15)] for _ in range(250)]
        self.stars = [Star() for _ in range(150)]
        
        self.local_wolves = []

        if multiplayer and self.network.connect():
            self.terrain = Terrain(seed=self.network.terrain_seed)
            self.player = Player()
            self.player.pos.x, self.player.pos.z = self.network.spawn_x, self.network.spawn_z
            self.player.pos.y = self.terrain.get_exact_height(self.player.pos.x, self.player.pos.z) + 1.6
            threading.Thread(target=self.network.receive_loop, daemon=True).start()
        else:
            print("ВКЛЮЧЕН ОДИНОЧНЫЙ РЕЖИМ")
            self.multiplayer = False
            self.terrain = Terrain()
            self.player = Player()
            self.player.pos.y = self.terrain.get_exact_height(0, 0) + 1.6
            for _ in range(10):
                self.local_wolves.append(LocalWolf(random.uniform(-40, 100), random.uniform(-40, 100)))
        
        self.renderer = Renderer3D(self.player)
        self.chunks, self.other_players, self.network_wolves = {}, {}, {}
        self.day_time, self.days_survived, self.network_update_timer = 0, 1, 0
        self.font = pygame.font.Font(None, int(20 * (HEIGHT / 600)))
        self.big_font = pygame.font.Font(None, int(48 * (HEIGHT / 600)))

    def get_chunk(self, cx, cz):
        if (cx, cz) not in self.chunks: self.chunks[(cx, cz)] = Chunk(cx, cz, self.terrain)
        return self.chunks[(cx, cz)]

    def get_nearby_chunks(self):
        pcx, pcz = math.floor(self.player.pos.x / 36), math.floor(self.player.pos.z / 36)
        return [self.get_chunk(pcx + dx, pcz + dz) for dx in range(-2, 3) for dz in range(-2, 3)]

    def is_day(self): return self.day_time < 500
    def is_purge(self): return (self.days_survived % 7 == 0) and not self.is_day()

    def check_tree_collision(self, new_x, new_z):
        for chunk in self.get_nearby_chunks():
            for tree in chunk.trees:
                if tree.chopped: continue
                dx, dz = new_x - tree.pos.x, new_z - tree.pos.z
                dist = math.hypot(dx, dz)
                min_dist = self.player.collision_radius + tree.collision_radius
                if dist < min_dist:
                    if dist > 0: return new_x + (dx/dist)*(min_dist-dist), new_z + (dz/dist)*(min_dist-dist)
                    else: 
                        a = random.uniform(0, 2 * math.pi)
                        return new_x + math.cos(a)*min_dist, new_z + math.sin(a)*min_dist
        return new_x, new_z

    def update(self, dt):
        if self.multiplayer and getattr(self.network, 'connected', False):
            self.network_update_timer += dt
            if self.network_update_timer > 0.05:
                self.network.send_position(self.player.pos.x, self.player.pos.y, self.player.pos.z, self.player.angle, self.player.pitch)
                self.network.send_stats(self.player.health, self.player.hunger, self.player.wood, self.player.berries)
                self.network_update_timer = 0
            
            self.day_time, self.days_survived = self.network.day_time, self.network.days_survived
            
            for pid, pdata in self.network.other_players.items():
                if pid not in self.other_players: self.other_players[pid] = OtherPlayer(pid, pdata['name'])
                other = self.other_players[pid]
                other.pos.x, other.pos.z, other.angle, other.pitch, other.health = pdata['x'], pdata['z'], pdata['angle'], pdata['pitch'], pdata['health']
                other.pos.y = pdata.get('y', self.terrain.get_exact_height(pdata['x'], pdata['z']) + 1.6)
                
            for pid in list(self.other_players):
                if pid not in self.network.other_players: del self.other_players[pid]
            
            for wdata in self.network.network_wolves:
                wid = wdata['id']
                if wid not in self.network_wolves: self.network_wolves[wid] = NetworkWolf(wid)
                w = self.network_wolves[wid]
                w.pos.x, w.pos.z, w.angle, w.health, w.alive, w.walk_phase = wdata['x'], wdata['z'], wdata['angle'], wdata['health'], wdata['alive'], wdata['walk_phase']
                w.pos.y = self.terrain.get_exact_height(wdata['x'], wdata['z'])
            alive_wolves = {w['id'] for w in self.network.network_wolves}
            for wid in list(self.network_wolves):
                if wid not in alive_wolves: del self.network_wolves[wid]
                
            for chunk in self.get_nearby_chunks():
                for tree in chunk.trees:
                    if (round(tree.pos.x, 1), round(tree.pos.z, 1)) in self.network.chopped_trees: tree.chopped, tree.faces_cache = True, None
                for berry in chunk.berries:
                    if (round(berry.pos.x, 1), round(berry.pos.z, 1)) in self.network.collected_berries: berry.collected = True
        else:
            self.day_time += dt * 2 
            if self.day_time >= 1000: self.day_time, self.days_survived = self.day_time - 1000, self.days_survived + 1
            
            for w in self.local_wolves:
                if w.alive:
                    w.pos.y = self.terrain.get_exact_height(w.pos.x, w.pos.z)
                    dist = math.hypot(self.player.pos.x - w.pos.x, self.player.pos.z - w.pos.z)
                    
                    if dist < 15 and not self.is_day():
                        w.walk_phase += dt * 8
                        w.angle = math.atan2(self.player.pos.z - w.pos.z, self.player.pos.x - w.pos.x)
                        if dist > 1.5:
                            w.pos.x += math.cos(w.angle) * 3.5 * dt
                            w.pos.z += math.sin(w.angle) * 3.5 * dt
                    else:
                        
                        w.walk_phase += dt * 2
                        w.pos.x += math.cos(w.angle) * 0.5 * dt
                        w.pos.z += math.sin(w.angle) * 0.5 * dt
                        if random.random() < 0.05: w.angle += random.uniform(-1, 1)

        if self.player.attack_timer > 0: self.player.attack_timer -= dt

        nx, nz = self.check_tree_collision(self.player.pos.x + self.player.velocity.x * dt, self.player.pos.z + self.player.velocity.z * dt)
        self.player.pos.x, self.player.pos.z = nx, nz
        
        self.player.velocity.y -= 25.0 * dt  
        new_y = self.player.pos.y + self.player.velocity.y * dt
        ground_y = self.terrain.get_exact_height(nx, nz) + 1.6
        
        if new_y <= ground_y:
            self.player.pos.y = ground_y
            self.player.velocity.y = 0
            self.player.is_grounded = True
        else:
            self.player.pos.y = new_y
            self.player.is_grounded = False

        dist_to_cave = math.hypot(nx - 150, nz - 150)
        target_intensity = max(0.0, min(1.0, (15 - self.player.pos.y) / 25.0)) if dist_to_cave < 65 and self.player.pos.y < 15 else 0.0
        self.cave_intensity += (target_intensity - self.cave_intensity) * dt * 2.0

        if self.cave_intensity > 0.1 and not self.cave_sound_playing: CAVE_CHANNEL.play(snd_cave, loops=-1); self.cave_sound_playing = True
        elif self.cave_intensity <= 0.1 and self.cave_sound_playing: CAVE_CHANNEL.fadeout(1000); self.cave_sound_playing = False
        if self.cave_sound_playing: CAVE_CHANNEL.set_volume(self.cave_intensity * 0.8)

        self.rain_check_timer += dt
        if self.rain_check_timer > 10.0:
            self.rain_check_timer = 0
            if not self.is_raining and random.random() < self.rain_chance:
                self.is_raining = True; self.rain_duration = random.uniform(120, 300) 
                RAIN_CHANNEL.play(snd_rain, loops=-1); RAIN_CHANNEL.set_volume(0) 
        if self.is_raining:
            self.rain_intensity = min(1.0, self.rain_intensity + dt * 0.2)
            self.rain_duration -= dt
            if self.rain_duration <= 0: self.is_raining = False
        else:
            self.rain_intensity = max(0.0, self.rain_intensity - dt * 0.2)
            if self.rain_intensity == 0 and RAIN_CHANNEL.get_busy(): RAIN_CHANNEL.stop()
        if self.rain_intensity > 0: RAIN_CHANNEL.set_volume(self.rain_intensity * 0.4)

        if self.rain_intensity > 0.5 and random.random() < 0.2 and len(self.puddles) < 60:
            rx, rz = self.player.pos.x + random.uniform(-25, 25), self.player.pos.z + random.uniform(-25, 25)
            if math.hypot(rx - 150, rz - 150) > 65 or self.terrain.get_exact_height(rx, rz) > 15:
                self.puddles.append(Puddle(rx, rz, self.terrain.get_exact_height(rx, rz)))
        
        for p in self.puddles[:]:
            if not self.is_raining:
                p.wetness -= dt * 2; p.size = (p.wetness / 100.0) * p.max_size; p.faces_cache = None 
                if p.wetness <= 0: self.puddles.remove(p)

        if self.rain_intensity > 0:
            for i in range(len(self.raindrops)):
                self.raindrops[i][1] -= dt * 30.0 
                if self.raindrops[i][1] < self.player.pos.y - 5: self.raindrops[i][1] = self.player.pos.y + random.uniform(15, 25)
                dx, dz = self.raindrops[i][0] - self.player.pos.x, self.raindrops[i][2] - self.player.pos.z
                if dx > 15: self.raindrops[i][0] -= 30
                elif dx < -15: self.raindrops[i][0] += 30
                if dz > 15: self.raindrops[i][2] -= 30
                elif dz < -15: self.raindrops[i][2] += 30

        if self.cave_intensity < 0.5 and not self.is_day(): 
            wolves = self.network_wolves.values() if self.multiplayer else self.local_wolves
            for w in wolves:
                if w.alive:
                    w.attack_cooldown -= dt
                    if math.hypot(w.pos.x - self.player.pos.x, w.pos.z - self.player.pos.z) < 1.5:
                        if w.attack_cooldown <= 0:
                            self.player.health -= 10; snd_wolf_bite.play(); w.attack_cooldown = 1.0 

        self.player.hunger -= dt * 0.3
        if self.player.hunger <= 0: self.player.hunger, self.player.health = 0, self.player.health - dt * 5

    def handle_input(self, keys, dt):
        if self.chat_active: return 
        
        mx = mz = 0
        if keys[pygame.K_d]: mx += math.cos(self.player.angle); mz += math.sin(self.player.angle)
        if keys[pygame.K_a]: mx -= math.cos(self.player.angle); mz -= math.sin(self.player.angle)
        if keys[pygame.K_s]: mx += math.cos(self.player.angle - math.pi/2); mz += math.sin(self.player.angle - math.pi/2)
        if keys[pygame.K_w]: mx += math.cos(self.player.angle + math.pi/2); mz += math.sin(self.player.angle + math.pi/2)
        l = math.hypot(mx, mz)
        if l > 0: mx /= l; mz /= l
        speed = 11.0 if keys[pygame.K_LSHIFT] else 5.5
        self.player.velocity.x += (mx * speed - self.player.velocity.x) * 15.0 * dt
        self.player.velocity.z += (mz * speed - self.player.velocity.z) * 15.0 * dt

    def attack(self):
        hit = False
        wolves = self.network_wolves.values() if self.multiplayer and self.network else self.local_wolves
        for w in wolves:
            if not w.alive: continue
            dx, dz = w.pos.x - self.player.pos.x, w.pos.z - self.player.pos.z
            if math.hypot(dx, dz) < 4.5 and abs(((math.atan2(dz, dx) - self.player.angle) + math.pi) % (2 * math.pi) - math.pi) < math.pi/4:
                if self.multiplayer and self.network:
                    self.network.send_attack_wolf(w.id, 15)
                    hit = True
                    if w.health <= 15: self.player.hunger = min(100, self.player.hunger + 30); snd_wolf_die.play()
                    else: snd_hit.play()
                else:
                    w.health -= 15
                    hit = True
                    if w.health <= 0:
                        w.alive = False
                        self.player.hunger = min(100, self.player.hunger + 30); snd_wolf_die.play()
                    else: snd_hit.play()
        if not hit: snd_swing.play()

    def chop_tree(self):
        for c in self.get_nearby_chunks():
            for t in c.trees:
                if not t.chopped and math.hypot(t.pos.x - self.player.pos.x, t.pos.z - self.player.pos.z) < 4:
                    t.chopped, t.faces_cache = True, None; self.player.wood += 5; snd_chop.play()
                    if getattr(self.network, 'connected', False): self.network.send_chop_tree(t.pos.x, t.pos.z)
                    return

    def collect_berry(self):
        for c in self.get_nearby_chunks():
            for b in c.berries:
                if not b.collected and math.hypot(b.pos.x - self.player.pos.x, b.pos.z - self.player.pos.z) < 3:
                    b.collected = True; self.player.berries += 1; snd_berry.play()
                    if getattr(self.network, 'connected', False): self.network.send_collect_berry(b.pos.x, b.pos.z)
                    return

    def get_sky_color(self):
        if self.is_purge():
            if self.day_time < 600: p = (self.day_time - 500) / 100.0; base = (int(20 + 80*p), int(20 - 20*p), int(40 - 40*p))
            elif self.day_time > 900: p = (self.day_time - 900) / 100.0; base = (int(100 - 80*p), int(20*p), int(40*p))
            else: base = (100, 0, 0)
        else:
            if self.day_time < 400: base = (130, 190, 255) 
            elif self.day_time < 500: p = (self.day_time - 400) / 100; base = (int(130 - 120*p), int(190 - 175*p), int(255 - 225*p))
            elif self.day_time < 900: base = (10, 15, 30)
            else: p = (self.day_time - 900) / 100; base = (int(10 + 120*p), int(15 + 175*p), int(30 + 225*p))
            
        rain_color = (90, 100, 110)
        return (
            int(base[0] * (1 - self.rain_intensity) + rain_color[0] * self.rain_intensity),
            int(base[1] * (1 - self.rain_intensity) + rain_color[1] * self.rain_intensity),
            int(base[2] * (1 - self.rain_intensity) + rain_color[2] * self.rain_intensity)
        )

    def draw(self):
        out_sky = self.get_sky_color()
        sky_col = (int(out_sky[0] * (1 - self.cave_intensity)), int(out_sky[1] * (1 - self.cave_intensity)), int(out_sky[2] * (1 - self.cave_intensity)))
        screen.fill(sky_col)

        if not self.is_day() and self.rain_intensity < 0.5 and self.cave_intensity < 0.1 and not self.is_purge():
            hw, hh = WIDTH/2, HEIGHT/2
            for star in self.stars:
                rel_pos = Vector3(self.player.pos.x + star.offset.x, self.player.pos.y + star.offset.y, self.player.pos.z + star.offset.z)
                cam = self.renderer.transform_to_camera(rel_pos)
                if cam[2] > self.renderer.near:
                    sx = int(hw + (cam[0] * self.renderer.fov) / cam[2])
                    sy = int(hh - (cam[1] * self.renderer.fov) / cam[2])
                    if 0 <= sx <= WIDTH and 0 <= sy <= HEIGHT:
                        screen.set_at((sx, sy), star.color)

        self.renderer.far = 90 - (50 * self.cave_intensity)
        if self.rain_intensity > 0: self.renderer.far *= (1.0 - 0.4 * self.rain_intensity)
        far_sq, px, pz = self.renderer.far**2, self.player.pos.x, self.player.pos.z
        all_faces = []
        def get_d(f): return sum(self.renderer.transform_to_camera(v)[2] for v in f.vertices) / len(f.vertices)

        for chunk in self.get_nearby_chunks():
            for f in chunk.faces:
                if (f.get_center().x - px)**2 + (f.get_center().z - pz)**2 < far_sq:
                    f.distance = get_d(f); 
                    if f.distance > -5: all_faces.append(f)
            for t in chunk.trees:
                if (t.pos.x - px)**2 + (t.pos.z - pz)**2 < far_sq:
                    for f in t.get_or_create_faces(self.renderer):
                        f.distance = get_d(f); 
                        if f.distance > -5: all_faces.append(f)
            for b in chunk.berries:
                if not b.collected and (b.pos.x - px)**2 + (b.pos.z - pz)**2 < far_sq:
                    for f in b.get_or_create_faces(self.renderer):
                        f.distance = get_d(f); 
                        if f.distance > -5: all_faces.append(f)
            for r in chunk.rocks:
                if (r.pos.x - px)**2 + (r.pos.z - pz)**2 < far_sq:
                    for f in r.get_or_create_faces(self.renderer):
                        f.distance = get_d(f); 
                        if f.distance > -5: all_faces.append(f)

        for p in self.puddles:
            if (p.pos.x - px)**2 + (p.pos.z - pz)**2 < far_sq:
                for f in p.get_or_create_faces(self.renderer):
                    f.distance = get_d(f);
                    if f.distance > -5: all_faces.append(f)

        if self.multiplayer:
            for o in self.other_players.values():
                if (o.pos.x - px)**2 + (o.pos.z - pz)**2 < far_sq:
                    for f in o.get_or_create_faces(self.renderer):
                        f.distance = get_d(f); 
                        if f.distance > -5: all_faces.append(f)
            for w in self.network_wolves.values():
                if w.alive and (w.pos.x - px)**2 + (w.pos.z - pz)**2 < far_sq:
                    for f in w.get_or_create_faces(self.renderer):
                        f.distance = get_d(f); 
                        if f.distance > -5: all_faces.append(f)
        else:
            for w in self.local_wolves:
                if w.alive and (w.pos.x - px)**2 + (w.pos.z - pz)**2 < far_sq:
                    for f in w.get_or_create_faces(self.renderer):
                        f.distance = get_d(f)
                        if f.distance > -5: all_faces.append(f)

        all_faces.sort(key=lambda f: f.distance, reverse=True)
        fov_lim = WIDTH / (2 * self.renderer.fov)

        for f in all_faces:
            cam = self.renderer.transform_to_camera(f.get_center())
            if cam[2] >= self.renderer.near and abs(cam[0]) <= cam[2] * fov_lim + 20:
                self.renderer.draw_polygon(f, sky_col)

        if self.rain_intensity > 0 and self.cave_intensity < 0.5:
            num_drops_to_draw = int(len(self.raindrops) * self.rain_intensity)
            hw, hh = WIDTH/2, HEIGHT/2
            for i in range(num_drops_to_draw):
                x, y, z = self.raindrops[i]
                cam1, cam2 = self.renderer.transform_to_camera(Vector3(x, y, z)), self.renderer.transform_to_camera(Vector3(x, y - 1.5, z)) 
                if cam1[2] > self.renderer.near and cam2[2] > self.renderer.near:
                    sx1, sy1 = int(hw + (cam1[0] * self.renderer.fov) / cam1[2]), int(hh - (cam1[1] * self.renderer.fov) / cam1[2])
                    sx2, sy2 = int(hw + (cam2[0] * self.renderer.fov) / cam2[2]), int(hh - (cam2[1] * self.renderer.fov) / cam2[2])
                    if 0 <= sx1 <= WIDTH and 0 <= sy2 <= HEIGHT:
                        pygame.draw.line(screen, (150, 160, 180), (sx1, sy1), (sx2, sy2), 1)

        if self.cave_intensity > 0:
            vignette = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            alpha = int(200 * self.cave_intensity)
            if self.cave_intensity > 0.7 and random.random() < 0.05: vignette.fill((0, 0, 0, 255))
            else: pygame.draw.rect(vignette, (0, 0, 0, alpha), (0, 0, WIDTH, HEIGHT), width=int(100*self.cave_intensity))
            screen.blit(vignette, (0, 0))

        if self.player.spear_equipped:
            pr = math.sin((self.player.attack_timer / 0.3) * math.pi) if self.player.attack_timer > 0 else 0
            tx, ty = WIDTH * 0.7 - pr * (WIDTH * 0.3), HEIGHT * 0.6 + pr * (HEIGHT * 0.1)
            bx, by = WIDTH * 0.9, HEIGHT + 50
            dx, dy = tx - bx, ty - by
            l = math.hypot(dx, dy)
            if l > 0:
                dirx, diry = dx/l, dy/l
                px, py = -diry, dirx
                pygame.draw.line(screen, BROWN, (bx, by), (tx, ty), int(12 * (HEIGHT / 600)))
                p1, p2, p3 = (tx+dirx*50, ty+diry*50), (tx+px*12, ty+py*12), (tx-px*12, ty-py*12)
                pygame.draw.polygon(screen, LIGHT_GRAY, [p1, p2, p3])
                pygame.draw.polygon(screen, BLACK, [p1, p2, p3], 2)

        cx, cy = WIDTH//2, HEIGHT//2
        for offset in [(-10,0,-3,0), (3,0,10,0), (0,-10,0,-3), (0,3,0,10)]:
            pygame.draw.line(screen, WHITE, (cx+offset[0], cy+offset[1]), (cx+offset[2], cy+offset[3]), 2)
        pygame.draw.circle(screen, WHITE, (cx, cy), 1)

        if self.is_purge(): screen.blit(self.big_font.render("BLOOD MOON", True, BRIGHT_RED), (WIDTH//2 - 100, 30))
        screen.blit(self.font.render(f"DAY {self.days_survived}", True, BRIGHT_RED if self.is_purge() else WHITE), (10, 10))
        if self.multiplayer and getattr(self.network, 'connected', False):
            screen.blit(self.font.render(f"ONLINE: {len(self.other_players) + 1}", True, BRIGHT_GREEN), (10, 30))

        if self.multiplayer and self.network:
            chat_y = HEIGHT - 80
            for msg in reversed(self.network.chat_messages):
                text_surf = self.font.render(f"[{msg['name']}]: {msg['msg']}", True, WHITE)
                bg = pygame.Surface((text_surf.get_width() + 10, text_surf.get_height() + 4), pygame.SRCALPHA)
                bg.fill((0, 0, 0, 120))
                screen.blit(bg, (10, chat_y))
                screen.blit(text_surf, (15, chat_y + 2))
                chat_y -= 25
                
        if self.chat_active:
            box = pygame.Surface((400, 30), pygame.SRCALPHA)
            box.fill((0, 0, 0, 200))
            screen.blit(box, (10, HEIGHT - 70))
            input_surf = self.font.render("> " + self.chat_input + ("_" if time.time() % 1 > 0.5 else ""), True, YELLOW)
            screen.blit(input_surf, (15, HEIGHT - 65))

        # HUD
        hud = pygame.Surface((WIDTH, int(24 * (HEIGHT / 600))), pygame.SRCALPHA)
        hud.fill((0, 0, 0, 180)); screen.blit(hud, (0, HEIGHT - int(24 * (HEIGHT / 600))))
        txts = [
            (f" HP: {int(self.player.health)}", RED if self.player.health < 30 else GREEN),
            (f" FOOD: {int(self.player.hunger)}", RED if self.player.hunger < 30 else YELLOW),
            (f" WOOD: {self.player.wood} BERRIES: {self.player.berries}", WHITE),
            (f" COORDS: X:{int(self.player.pos.x)} Y:{int(self.player.pos.y)} Z:{int(self.player.pos.z)}", LIGHT_GRAY)
        ]
        x_off, y_pos = 10, HEIGHT - int(20 * (HEIGHT / 600))
        for t, c in txts:
            s = self.font.render(t, True, c); screen.blit(s, (x_off, y_pos)); x_off += s.get_width() + 15
        s = self.font.render("Space:Jump | F:Chop | C:Pick | B:Eat | 1:Spear", True, LIGHT_GRAY)
        screen.blit(s, (WIDTH - s.get_width() - 10, y_pos))

        if self.player.health <= 0:
            o = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); o.fill((0, 0, 0, 200)); screen.blit(o, (0, 0))
            screen.blit(self.big_font.render("YOU DIED", True, BRIGHT_RED), (WIDTH//2 - 60, HEIGHT//2 - 40))
            screen.blit(self.font.render("Press T to restart", True, WHITE), (WIDTH//2 - 60, HEIGHT//2))

def handle_resize(event):
    global WIDTH, HEIGHT, screen, game
    WIDTH, HEIGHT = event.w, event.h
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE | pygame.HWSURFACE | pygame.DOUBLEBUF)
    if hasattr(game, 'renderer'):
        game.renderer.cx_max, game.renderer.cy_max = WIDTH+50, HEIGHT+50
        game.font, game.big_font = pygame.font.Font(None, int(20 * (HEIGHT/600))), pygame.font.Font(None, int(48 * (HEIGHT/600)))

def main():
    global game
    game = Game(multiplayer=True)
    running, paused = True, False

    while running:
        dt = clock.tick(60) / 1000.0
        
        if not paused and not game.chat_active:
            if pygame.mouse.get_visible(): pygame.mouse.set_visible(False)
            if not pygame.event.get_grab(): pygame.event.set_grab(True)
            
        for e in pygame.event.get():
            if e.type == pygame.QUIT: running = False
            if e.type == pygame.VIDEORESIZE: handle_resize(e); continue
            
            if e.type == pygame.MOUSEBUTTONDOWN:
                if paused:
                    paused = False; pygame.mouse.set_visible(False); pygame.event.set_grab(True); pygame.mouse.get_rel() 
                elif e.button == 1 and game.player.spear_equipped and game.player.attack_timer <= 0 and not game.chat_active:
                    game.player.attack_timer = 0.3; game.attack()
                    
            if e.type == pygame.KEYDOWN:
                if game.chat_active:
                    if e.key == pygame.K_RETURN:
                        if game.chat_input.strip() and game.network:
                            game.network.send_chat(game.chat_input)
                        game.chat_active = False
                        game.chat_input = ""
                        pygame.event.set_grab(True); pygame.mouse.get_rel()
                    elif e.key == pygame.K_ESCAPE:
                        game.chat_active = False; game.chat_input = ""
                        pygame.event.set_grab(True); pygame.mouse.get_rel()
                    elif e.key == pygame.K_BACKSPACE:
                        game.chat_input = game.chat_input[:-1]
                    else:
                        game.chat_input += e.unicode
                    continue 
                
                if e.key == pygame.K_ESCAPE:
                    paused = not paused
                    if paused:
                        pygame.mouse.set_visible(True); pygame.event.set_grab(False)
                    else:
                        pygame.mouse.set_visible(False); pygame.event.set_grab(True); pygame.mouse.get_rel()
                        
                if not paused:
                    if e.key == pygame.K_RETURN and game.multiplayer:
                        game.chat_active = True
                        pygame.event.set_grab(False)
                    if e.key == pygame.K_SPACE and game.player.is_grounded:
                        game.player.velocity.y = 9.0  
                    if e.key == pygame.K_1: game.player.spear_equipped = not game.player.spear_equipped
                    if e.key == pygame.K_f: game.chop_tree() 
                    if e.key == pygame.K_c: game.collect_berry()
                    if e.key == pygame.K_b and game.player.berries > 0:
                        game.player.berries -= 1; game.player.hunger = min(100, game.player.hunger + 25); snd_berry.play()
                
                if e.key == pygame.K_t and game.player.health <= 0:
                    if getattr(game.network, 'connected', False): game.network.disconnect()
                    game = Game(multiplayer=game.multiplayer)
                    paused = False; pygame.mouse.set_visible(False); pygame.event.set_grab(True); pygame.mouse.get_rel()
                    
            if e.type == pygame.MOUSEMOTION and not paused and not game.chat_active:
                game.player.angle += e.rel[0] * 0.002
                game.player.pitch = max(-math.pi/2.5, min(math.pi/2.5, game.player.pitch - e.rel[1] * 0.002))

        if not paused: game.handle_input(pygame.key.get_pressed(), dt); game.update(dt)
        game.draw()
        
        if paused:
            o = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); o.fill((0, 0, 0, 100)); screen.blit(o, (0, 0))
            screen.blit(game.big_font.render("PAUSED", True, WHITE), (WIDTH//2 - 50, HEIGHT//2))
            
        pygame.display.flip()

    if getattr(game.network, 'connected', False): game.network.disconnect()
    pygame.quit()

if __name__ == "__main__": main()