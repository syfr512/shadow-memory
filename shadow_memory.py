"""
SHADOW MEMORY: A self-contained 2D top-down horror/puzzle game made with Pygame.

- No external image/audio assets.
- No cloud APIs.
- All pixel-art sprites, tiles, UI, particles, lighting, maze, puzzles, and AI are generated in code.

Controls:
    WASD / Arrow Keys  : Move
    E                  : Interact with artifacts / exit
    Esc                : Return to menu from gameplay or popup

Run:
    python shadow_memory_horror.py
"""

import math
import random
import sys
import heapq
from collections import deque

try:
    import pygame
except ImportError as exc:
    raise SystemExit(
        "Pygame is required to run this game. Install it with: pip install pygame"
    ) from exc

# ----------------------------- GLOBAL CONFIG ----------------------------- #

WINDOW_W, WINDOW_H = 960, 720
FPS = 60
TILE = 32
GRID_W, GRID_H = 29, 19  # odd dimensions for clean maze carving
WORLD_W, WORLD_H = GRID_W * TILE, GRID_H * TILE
GRID_X = (WINDOW_W - WORLD_W) // 2
GRID_Y = 88
HUD_H = 74

Vec2 = pygame.math.Vector2


class State:
    MENU = "MENU"
    OPTIONS = "OPTIONS"
    GAMEPLAY = "GAMEPLAY"
    PUZZLE_POPUP = "PUZZLE_POPUP"
    GAME_OVER = "GAME_OVER"
    VICTORY = "VICTORY"


class EnemyState:
    PATROL = "PATROL"
    CHASE = "CHASE"
    RANGED = "RANGED ATTACK"
    MELEE = "MELEE STAB"


class Palette:
    BG = (6, 8, 14)
    PANEL = (13, 16, 26)
    PANEL_2 = (22, 25, 38)
    PANEL_3 = (31, 35, 53)
    TEXT = (226, 232, 245)
    MUTED = (133, 145, 166)
    ACCENT = (120, 78, 255)
    ACCENT_2 = (89, 214, 255)
    DANGER = (224, 48, 78)
    WARNING = (255, 195, 77)
    GOOD = (89, 230, 156)
    DARK_RED = (72, 16, 29)
    BLACK = (0, 0, 0)


# ----------------------------- SMALL HELPERS ----------------------------- #


def clamp(value, low, high):
    return max(low, min(high, value))


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def cell_to_pos(cell):
    x, y = cell
    return Vec2(GRID_X + x * TILE + TILE // 2, GRID_Y + y * TILE + TILE // 2)


def pos_to_cell(pos):
    return (int((pos.x - GRID_X) // TILE), int((pos.y - GRID_Y) // TILE))


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def euclidean(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def draw_text(surface, text, font, color, pos, align="topleft"):
    img = font.render(str(text), True, color)
    rect = img.get_rect()
    setattr(rect, align, pos)
    surface.blit(img, rect)
    return rect


def make_font(size, bold=False):
    # Consolas gives a clean retro-tech look; SysFont falls back safely.
    return pygame.font.SysFont("consolas", size, bold=bold)


def bresenham_cells(start, end):
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        yield (x, y)
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


# ----------------------------- PROCEDURAL ART ---------------------------- #


class Assets:
    def __init__(self):
        self.floor_tiles = []
        self.wall_tiles = []
        self.player_frames = []
        self.enemy_frames = {}
        self.artifact = None
        self.exit_locked = None
        self.exit_unlocked = None
        self.projectile = None
        self.key_icon = None
        self.fragment_icon = None
        self._generate_all()

    def _surface(self, w=TILE, h=TILE, alpha=True):
        flags = pygame.SRCALPHA if alpha else 0
        return pygame.Surface((w, h), flags).convert_alpha() if alpha else pygame.Surface((w, h)).convert()

    def _generate_all(self):
        self.floor_tiles = [self._make_floor(i) for i in range(8)]
        self.wall_tiles = [self._make_wall(i) for i in range(8)]
        self.player_frames = [self._make_player(i) for i in range(4)]
        self.enemy_frames = {
            EnemyState.PATROL: self._make_enemy((76, 20, 34), (244, 60, 90), 0),
            EnemyState.CHASE: self._make_enemy((110, 17, 35), (255, 36, 72), 1),
            EnemyState.RANGED: self._make_enemy((99, 25, 58), (255, 99, 120), 2),
            EnemyState.MELEE: self._make_enemy((150, 20, 33), (255, 210, 210), 3),
        }
        self.artifact = self._make_artifact()
        self.exit_locked = self._make_exit(False)
        self.exit_unlocked = self._make_exit(True)
        self.projectile = self._make_projectile()
        self.key_icon = self._make_key_icon()
        self.fragment_icon = self._make_fragment_icon()

    def _make_floor(self, seed):
        rng = random.Random(1000 + seed)
        surf = self._surface(alpha=False)
        base = (18 + seed % 3, 20 + seed % 4, 27 + seed % 3)
        surf.fill(base)
        # Large stone slabs
        pygame.draw.rect(surf, (13, 15, 21), (0, 0, 32, 1))
        pygame.draw.rect(surf, (27, 29, 38), (0, 31, 32, 1))
        pygame.draw.rect(surf, (10, 12, 18), (0, 0, 1, 32))
        pygame.draw.rect(surf, (25, 27, 35), (31, 0, 1, 32))
        for _ in range(18):
            x = rng.randrange(2, 30)
            y = rng.randrange(2, 30)
            col = rng.choice([(24, 27, 36), (12, 14, 21), (31, 28, 35), (20, 23, 31)])
            surf.set_at((x, y), col)
        # Hairline cracks
        for _ in range(2):
            x = rng.randrange(4, 27)
            y = rng.randrange(5, 27)
            length = rng.randrange(4, 10)
            for i in range(length):
                if 0 <= x + i < 32 and 0 <= y + (i // 3) < 32:
                    surf.set_at((x + i, y + (i // 3)), (7, 9, 14))
        return surf.convert()

    def _make_wall(self, seed):
        rng = random.Random(2000 + seed)
        surf = self._surface(alpha=False)
        surf.fill((26, 23, 31))
        # Shadowed block base
        pygame.draw.rect(surf, (15, 14, 21), (0, 0, 32, 32))
        pygame.draw.rect(surf, (47, 42, 54), (2, 2, 28, 27))
        pygame.draw.rect(surf, (28, 25, 34), (2, 24, 28, 6))
        # Brick rows
        rows = [(3, 7), (11, 7), (19, 7)]
        offset = 0 if seed % 2 == 0 else 7
        for y, h in rows:
            x = -offset
            while x < 32:
                w = rng.choice([10, 12, 14])
                col = rng.choice([(55, 48, 61), (62, 54, 67), (45, 40, 53)])
                pygame.draw.rect(surf, col, (x + 1, y, w, h))
                pygame.draw.line(surf, (23, 21, 31), (x, y + h), (x + w, y + h))
                pygame.draw.line(surf, (75, 65, 82), (x + 1, y), (x + w - 1, y))
                x += w
        # Moss / grime pixels
        for _ in range(20):
            x = rng.randrange(1, 31)
            y = rng.randrange(2, 30)
            col = rng.choice([(30, 50, 42), (21, 36, 32), (79, 54, 62), (15, 12, 20)])
            surf.set_at((x, y), col)
        # Heavy bottom shadow
        pygame.draw.rect(surf, (8, 8, 13), (0, 29, 32, 3))
        return surf.convert()

    def _make_player(self, frame):
        surf = self._surface()
        # Shadow
        pygame.draw.ellipse(surf, (0, 0, 0, 110), (7, 24, 18, 6))
        # Coat / body
        bob = 1 if frame in (1, 2) else 0
        pygame.draw.rect(surf, (34, 46, 69), (10, 12 + bob, 12, 14))
        pygame.draw.rect(surf, (18, 25, 42), (8, 16 + bob, 4, 10))
        pygame.draw.rect(surf, (19, 25, 40), (20, 16 + bob, 4, 10))
        pygame.draw.rect(surf, (69, 90, 129), (12, 13 + bob, 8, 3))
        pygame.draw.rect(surf, (12, 16, 27), (10, 24 + bob, 5, 4))
        pygame.draw.rect(surf, (12, 16, 27), (17, 24 + bob, 5, 4))
        # Head / hair
        pygame.draw.rect(surf, (53, 37, 32), (10, 6 + bob, 12, 8))
        pygame.draw.rect(surf, (201, 159, 119), (12, 8 + bob, 8, 7))
        pygame.draw.rect(surf, (42, 29, 26), (9, 5 + bob, 14, 4))
        pygame.draw.rect(surf, (235, 234, 190), (13, 10 + bob, 2, 2))
        pygame.draw.rect(surf, (235, 234, 190), (18, 10 + bob, 2, 2))
        # Little flashlight piece
        pygame.draw.rect(surf, (128, 133, 146), (22, 16 + bob, 5, 3))
        pygame.draw.rect(surf, (247, 222, 124), (27, 16 + bob, 2, 3))
        return surf

    def _make_enemy(self, cloak_color, eye_color, variant):
        surf = self._surface()
        pygame.draw.ellipse(surf, (0, 0, 0, 140), (5, 25, 22, 6))
        # Cloak silhouette
        pygame.draw.rect(surf, (18, 10, 17), (9, 7, 14, 20))
        pygame.draw.rect(surf, cloak_color, (10, 9, 12, 18))
        pygame.draw.rect(surf, (32, 12, 22), (7, 14, 5, 11))
        pygame.draw.rect(surf, (32, 12, 22), (20, 14, 5, 11))
        # Hood / face
        pygame.draw.rect(surf, (7, 7, 12), (10, 5, 12, 9))
        pygame.draw.rect(surf, eye_color, (12, 10, 3, 2))
        pygame.draw.rect(surf, eye_color, (18, 10, 3, 2))
        pygame.draw.rect(surf, (255, 255, 255), (25, 17, 2, 7))
        # Blade / weapon changes by state
        if variant == 2:
            pygame.draw.rect(surf, (210, 90, 120), (23, 14, 7, 2))
            pygame.draw.rect(surf, (255, 180, 210), (28, 14, 2, 2))
        elif variant == 3:
            pygame.draw.line(surf, (255, 235, 235), (22, 13), (31, 25), 2)
            pygame.draw.line(surf, (255, 70, 90), (24, 15), (29, 23), 1)
        else:
            pygame.draw.line(surf, (210, 210, 218), (22, 16), (28, 24), 2)
        # Ragged pixels
        pygame.draw.rect(surf, (9, 6, 11), (8, 26, 4, 2))
        pygame.draw.rect(surf, (9, 6, 11), (18, 26, 5, 2))
        return surf

    def _make_artifact(self):
        surf = self._surface()
        pygame.draw.ellipse(surf, (0, 0, 0, 130), (5, 25, 22, 6))
        pygame.draw.rect(surf, (46, 42, 55), (8, 21, 16, 6))
        pygame.draw.rect(surf, (75, 69, 92), (10, 17, 12, 5))
        pygame.draw.rect(surf, (49, 109, 113), (12, 11, 8, 8))
        pygame.draw.rect(surf, (111, 244, 222), (14, 9, 4, 12))
        pygame.draw.rect(surf, (235, 255, 240), (15, 10, 2, 3))
        pygame.draw.rect(surf, (26, 58, 64), (11, 14, 2, 5))
        pygame.draw.rect(surf, (26, 58, 64), (19, 14, 2, 5))
        return surf

    def _make_exit(self, unlocked):
        surf = self._surface()
        frame = (89, 214, 255) if unlocked else (118, 67, 88)
        core = (17, 40, 50) if unlocked else (34, 18, 27)
        glow = (160, 245, 255) if unlocked else (224, 48, 78)
        pygame.draw.rect(surf, (0, 0, 0, 110), (5, 3, 22, 29))
        pygame.draw.rect(surf, frame, (6, 2, 20, 30))
        pygame.draw.rect(surf, core, (9, 5, 14, 25))
        pygame.draw.rect(surf, (6, 9, 15), (11, 8, 10, 19))
        pygame.draw.rect(surf, glow, (15, 15, 2, 5))
        if not unlocked:
            pygame.draw.rect(surf, (202, 168, 77), (12, 14, 8, 7))
            pygame.draw.rect(surf, (62, 38, 28), (14, 16, 4, 4))
        else:
            pygame.draw.line(surf, glow, (12, 9), (20, 23), 1)
            pygame.draw.line(surf, glow, (20, 9), (12, 23), 1)
        return surf

    def _make_projectile(self):
        surf = self._surface(10, 10)
        pygame.draw.circle(surf, (255, 57, 89), (5, 5), 4)
        pygame.draw.circle(surf, (255, 218, 229), (5, 5), 2)
        return surf

    def _make_key_icon(self):
        surf = self._surface(24, 24)
        pygame.draw.circle(surf, (235, 204, 91), (8, 10), 5, 2)
        pygame.draw.rect(surf, (235, 204, 91), (12, 9, 9, 3))
        pygame.draw.rect(surf, (235, 204, 91), (18, 12, 2, 4))
        pygame.draw.rect(surf, (180, 126, 43), (13, 12, 5, 2))
        return surf

    def _make_fragment_icon(self):
        surf = self._surface(22, 22)
        points = [(11, 1), (18, 8), (15, 19), (7, 18), (3, 9)]
        pygame.draw.polygon(surf, (86, 231, 222), points)
        pygame.draw.polygon(surf, (235, 255, 250), [(11, 4), (14, 8), (11, 11), (8, 8)])
        pygame.draw.polygon(surf, (24, 92, 104), points, 2)
        return surf


# ----------------------------- UI COMPONENTS ----------------------------- #


class Button:
    def __init__(self, rect, text, callback, font, accent=Palette.ACCENT):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.callback = callback
        self.font = font
        self.accent = accent
        self.hover_t = 0.0

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.callback()

    def update(self, dt):
        hovering = self.rect.collidepoint(pygame.mouse.get_pos())
        target = 1.0 if hovering else 0.0
        self.hover_t = lerp(self.hover_t, target, 1 - math.pow(0.001, dt))

    def draw(self, surface):
        t = smoothstep(self.hover_t)
        grow = int(4 * t)
        rect = self.rect.inflate(grow * 2, grow * 2)
        base = tuple(int(lerp(a, b, t)) for a, b in zip(Palette.PANEL_2, self.accent))
        border = tuple(int(lerp(a, b, t)) for a, b in zip(Palette.PANEL_3, Palette.ACCENT_2))
        shadow = rect.move(0, 5)
        pygame.draw.rect(surface, (0, 0, 0), shadow, border_radius=14)
        pygame.draw.rect(surface, base, rect, border_radius=14)
        pygame.draw.rect(surface, border, rect, width=2, border_radius=14)
        draw_text(surface, self.text, self.font, Palette.TEXT, rect.center, align="center")


# ----------------------------- MAZE + PATHING ----------------------------- #


class Maze:
    def __init__(self, width, height, artifact_count=3):
        self.w = width
        self.h = height
        self.grid = [[1 for _ in range(width)] for _ in range(height)]
        self.walkable = []
        self.player_start = (1, 1)
        self.enemy_start = (width - 2, height - 2)
        self.exit_cell = (width - 2, height - 2)
        self.artifacts = []
        self.artifact_count = artifact_count
        self._generate_valid_maze()

    def _generate_valid_maze(self):
        # Try multiple layouts. The constraints are strict so the game never spawns trapped.
        for _ in range(150):
            self._carve_backtracker()
            self._add_loops(loop_chance=0.075)
            self.walkable = [(x, y) for y in range(self.h) for x in range(self.w) if self.grid[y][x] == 0]
            self.player_start = self._choose_start()
            distances = self._bfs_distances(self.player_start)
            if len(distances) < len(self.walkable) * 0.96:
                continue
            far_cells = sorted(distances.items(), key=lambda item: item[1], reverse=True)
            if not far_cells or far_cells[0][1] < 22:
                continue
            self.exit_cell = far_cells[0][0]
            self.enemy_start = self._choose_enemy_start(distances, far_cells)
            self.artifacts = self._choose_artifacts(distances)
            if self.enemy_start and len(self.artifacts) >= self.artifact_count:
                return
        # Fallback: still connected because the backtracker creates a perfect maze.
        self.walkable = [(x, y) for y in range(self.h) for x in range(self.w) if self.grid[y][x] == 0]
        distances = self._bfs_distances(self.player_start)
        far_cells = sorted(distances.items(), key=lambda item: item[1], reverse=True)
        self.exit_cell = far_cells[0][0]
        self.enemy_start = far_cells[min(8, len(far_cells) - 1)][0]
        self.artifacts = [cell for cell, _ in far_cells[5:5 + self.artifact_count]]

    def _carve_backtracker(self):
        self.grid = [[1 for _ in range(self.w)] for _ in range(self.h)]
        rng = random.Random()
        start = (1, 1)
        self.grid[start[1]][start[0]] = 0
        stack = [start]
        dirs = [(2, 0), (-2, 0), (0, 2), (0, -2)]
        while stack:
            x, y = stack[-1]
            neighbors = []
            rng.shuffle(dirs)
            for dx, dy in dirs:
                nx, ny = x + dx, y + dy
                if 1 <= nx < self.w - 1 and 1 <= ny < self.h - 1 and self.grid[ny][nx] == 1:
                    neighbors.append((nx, ny, dx, dy))
            if neighbors:
                nx, ny, dx, dy = rng.choice(neighbors)
                self.grid[y + dy // 2][x + dx // 2] = 0
                self.grid[ny][nx] = 0
                stack.append((nx, ny))
            else:
                stack.pop()

    def _add_loops(self, loop_chance):
        rng = random.Random()
        for y in range(1, self.h - 1):
            for x in range(1, self.w - 1):
                if self.grid[y][x] == 1 and rng.random() < loop_chance:
                    horizontal = self.grid[y][x - 1] == 0 and self.grid[y][x + 1] == 0
                    vertical = self.grid[y - 1][x] == 0 and self.grid[y + 1][x] == 0
                    if horizontal or vertical:
                        self.grid[y][x] = 0

    def _choose_start(self):
        preferred = [(1, 1), (1, 3), (3, 1), (3, 3)]
        for cell in preferred:
            if self.passable(cell):
                return cell
        return random.choice(self.walkable)

    def _choose_enemy_start(self, distances, far_cells):
        max_dist = far_cells[0][1]
        candidates = [
            cell for cell, dist in far_cells
            if dist > max_dist * 0.55 and manhattan(cell, self.exit_cell) > 6 and cell != self.exit_cell
        ]
        return random.choice(candidates[:20]) if candidates else far_cells[min(5, len(far_cells) - 1)][0]

    def _choose_artifacts(self, distances):
        max_dist = max(distances.values()) if distances else 1
        candidates = [
            cell for cell, dist in sorted(distances.items(), key=lambda item: item[1], reverse=True)
            if dist > max_dist * 0.32
            and cell != self.exit_cell
            and cell != self.enemy_start
            and manhattan(cell, self.player_start) > 8
            and manhattan(cell, self.exit_cell) > 4
        ]
        chosen = []
        rng = random.Random()
        rng.shuffle(candidates)
        for cell in candidates:
            if all(manhattan(cell, other) >= 7 for other in chosen):
                chosen.append(cell)
                if len(chosen) >= self.artifact_count:
                    break
        if len(chosen) < self.artifact_count:
            for cell in candidates:
                if cell not in chosen:
                    chosen.append(cell)
                    if len(chosen) >= self.artifact_count:
                        break
        return chosen

    def _bfs_distances(self, start):
        q = deque([start])
        dist = {start: 0}
        while q:
            cell = q.popleft()
            for nb in self.neighbors(cell):
                if nb not in dist:
                    dist[nb] = dist[cell] + 1
                    q.append(nb)
        return dist

    def in_bounds(self, cell):
        x, y = cell
        return 0 <= x < self.w and 0 <= y < self.h

    def passable(self, cell):
        x, y = cell
        return self.in_bounds(cell) and self.grid[y][x] == 0

    def neighbors(self, cell):
        x, y = cell
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (x + dx, y + dy)
            if self.passable(nb):
                yield nb

    def has_los(self, a, b):
        if not self.passable(a) or not self.passable(b):
            return False
        for i, cell in enumerate(bresenham_cells(a, b)):
            if i == 0 or cell == b:
                continue
            if not self.passable(cell):
                return False
        return True

    def astar(self, start, goal):
        if not self.passable(start) or not self.passable(goal):
            return []
        if start == goal:
            return [start]
        counter = 0
        frontier = []
        heapq.heappush(frontier, (0, counter, start))
        came_from = {start: None}
        g_score = {start: 0}
        while frontier:
            _, _, current = heapq.heappop(frontier)
            if current == goal:
                break
            for nb in self.neighbors(current):
                new_cost = g_score[current] + 1
                if nb not in g_score or new_cost < g_score[nb]:
                    g_score[nb] = new_cost
                    counter += 1
                    priority = new_cost + manhattan(nb, goal)
                    heapq.heappush(frontier, (priority, counter, nb))
                    came_from[nb] = current
        if goal not in came_from:
            return []
        path = []
        node = goal
        while node is not None:
            path.append(node)
            node = came_from[node]
        path.reverse()
        return path


# ------------------------------ GAME OBJECTS ----------------------------- #


class Particle:
    def __init__(self, pos, vel, color, life=0.55, size=3):
        self.pos = Vec2(pos)
        self.vel = Vec2(vel)
        self.color = color
        self.life = life
        self.max_life = life
        self.size = size

    def update(self, dt):
        self.life -= dt
        self.pos += self.vel * dt
        self.vel *= math.pow(0.08, dt)
        return self.life > 0

    def draw(self, surface, offset=(0, 0)):
        if self.life <= 0:
            return
        alpha = int(255 * clamp(self.life / self.max_life, 0, 1))
        col = (*self.color, alpha)
        s = max(1, int(self.size * clamp(self.life / self.max_life, 0, 1)))
        tmp = pygame.Surface((s * 2 + 2, s * 2 + 2), pygame.SRCALPHA)
        pygame.draw.rect(tmp, col, (1, 1, s * 2, s * 2))
        surface.blit(tmp, (int(self.pos.x + offset[0] - s), int(self.pos.y + offset[1] - s)))


class Projectile:
    def __init__(self, pos, direction, speed, damage=1):
        self.pos = Vec2(pos)
        direction = Vec2(direction)
        self.vel = direction.normalize() * speed if direction.length_squared() else Vec2(0, 0)
        self.damage = damage
        self.life = 2.0
        self.dead = False
        self.radius = 6

    def update(self, game, dt):
        if self.dead:
            return False
        self.life -= dt
        if self.life <= 0:
            self.dead = True
            return False
        self.pos += self.vel * dt
        cell = pos_to_cell(self.pos)
        if not game.maze.passable(cell):
            self.dead = True
            game.spawn_burst(self.pos, Palette.DANGER, amount=12, speed=95)
            return False
        if game.player.invuln <= 0 and self.pos.distance_to(game.player.pos) < 15:
            self.dead = True
            game.damage_player(self.damage, "The shot tore through you.")
            game.spawn_burst(self.pos, (255, 80, 105), amount=18, speed=130)
            return False
        return True

    def draw(self, surface, assets, offset=(0, 0)):
        rect = assets.projectile.get_rect(center=(int(self.pos.x + offset[0]), int(self.pos.y + offset[1])))
        surface.blit(assets.projectile, rect)


class Player:
    def __init__(self, cell):
        self.cell = cell
        self.pos = cell_to_pos(cell)
        self.target_cell = cell
        self.target_pos = Vec2(self.pos)
        self.moving = False
        self.direction = Vec2(1, 0)
        self.hp = 3
        self.max_hp = 3
        self.invuln = 0.0
        self.anim_t = 0.0
        self.move_speed = 185.0

    def handle_input(self, game):
        if self.moving:
            return
        keys = pygame.key.get_pressed()
        move = None
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            move = (0, -1)
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            move = (0, 1)
        elif keys[pygame.K_LEFT] or keys[pygame.K_a]:
            move = (-1, 0)
        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            move = (1, 0)
        if move:
            nx = self.cell[0] + move[0]
            ny = self.cell[1] + move[1]
            if game.maze.passable((nx, ny)):
                self.target_cell = (nx, ny)
                self.target_pos = cell_to_pos(self.target_cell)
                self.direction = Vec2(move)
                self.moving = True
                game.make_noise(self.target_cell, strength=1.0)

    def update(self, game, dt):
        self.anim_t += dt
        self.invuln = max(0.0, self.invuln - dt)
        self.handle_input(game)
        if self.moving:
            delta = self.target_pos - self.pos
            dist = delta.length()
            step = self.move_speed * dt
            if dist <= step or dist < 0.5:
                self.pos = Vec2(self.target_pos)
                self.cell = self.target_cell
                self.moving = False
            else:
                self.pos += delta.normalize() * step

    def draw(self, surface, assets, offset=(0, 0)):
        frame = int(self.anim_t * 8) % len(assets.player_frames)
        surf = assets.player_frames[frame if self.moving else 0]
        if self.invuln > 0 and int(self.invuln * 16) % 2 == 0:
            tint = surf.copy()
            tint.fill((255, 80, 100, 80), special_flags=pygame.BLEND_RGBA_ADD)
            surf = tint
        rect = surf.get_rect(center=(int(self.pos.x + offset[0]), int(self.pos.y + offset[1])))
        surface.blit(surf, rect)


class Enemy:
    def __init__(self, cell, difficulty="Normal"):
        self.cell = cell
        self.pos = cell_to_pos(cell)
        self.target_cell = cell
        self.target_pos = Vec2(self.pos)
        self.state = EnemyState.PATROL
        self.path = []
        self.patrol_target = None
        self.repath_timer = 0.0
        self.attack_cooldown = 0.8
        self.melee_cooldown = 0.0
        self.state_lock = 0.0
        self.last_player_cell = None
        self.anim_t = 0.0
        self.set_difficulty(difficulty)

    def set_difficulty(self, difficulty):
        if difficulty == "Easy":
            self.patrol_speed = 78.0
            self.chase_speed = 112.0
            self.bullet_speed = 310.0
            self.attack_interval = 1.55
            self.hearing_radius = 5.0
        elif difficulty == "Hard":
            self.patrol_speed = 95.0
            self.chase_speed = 150.0
            self.bullet_speed = 420.0
            self.attack_interval = 0.82
            self.hearing_radius = 8.0
        else:
            self.patrol_speed = 86.0
            self.chase_speed = 132.0
            self.bullet_speed = 365.0
            self.attack_interval = 1.12
            self.hearing_radius = 6.5

    def update(self, game, dt):
        self.anim_t += dt
        self.repath_timer = max(0.0, self.repath_timer - dt)
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        self.melee_cooldown = max(0.0, self.melee_cooldown - dt)
        self.state_lock = max(0.0, self.state_lock - dt)

        player = game.player
        dist_cells = euclidean(self.cell, player.cell)
        los = game.maze.has_los(self.cell, player.cell)
        heard_noise = (
            game.noise_timer > 0
            and game.last_noise_cell is not None
            and euclidean(self.cell, game.last_noise_cell) <= self.hearing_radius
        )

        if self.cell == player.cell and self.melee_cooldown <= 0:
            self._melee_stab(game)
            return

        if self.state == EnemyState.RANGED and self.state_lock > 0:
            return

        if los and dist_cells <= 5.0 and self.attack_cooldown <= 0:
            self._ranged_attack(game)
            return

        if los or heard_noise:
            if self.state != EnemyState.CHASE:
                self.path = []
                self.repath_timer = 0.0
            self.state = EnemyState.CHASE
        elif self.state != EnemyState.PATROL:
            self.state = EnemyState.PATROL
            self.path = []
            self.patrol_target = None

        if self.state == EnemyState.CHASE:
            self._update_chase(game, dt)
        elif self.state == EnemyState.PATROL:
            self._update_patrol(game, dt)

        if self.cell == player.cell and self.melee_cooldown <= 0:
            self._melee_stab(game)

    def _update_chase(self, game, dt):
        if self.repath_timer <= 0 or self.last_player_cell != game.player.cell or not self.path:
            self.last_player_cell = game.player.cell
            path = game.maze.astar(self.cell, game.player.cell)
            self.path = path[1:] if len(path) > 1 else []
            self.repath_timer = 0.22
        self._follow_path(game, dt, self.chase_speed)

    def _update_patrol(self, game, dt):
        if not self.path:
            self.patrol_target = self._pick_patrol_target(game)
            path = game.maze.astar(self.cell, self.patrol_target)
            self.path = path[1:] if len(path) > 1 else []
        self._follow_path(game, dt, self.patrol_speed)

    def _pick_patrol_target(self, game):
        # Pick from reachable walkable cells, moderately far to make patrols purposeful.
        candidates = [c for c in game.maze.walkable if manhattan(c, self.cell) > 8]
        if not candidates:
            candidates = game.maze.walkable
        for _ in range(20):
            c = random.choice(candidates)
            if game.maze.astar(self.cell, c):
                return c
        return random.choice(game.maze.walkable)

    def _follow_path(self, game, dt, speed):
        if not self.path:
            return
        next_cell = self.path[0]
        self.target_cell = next_cell
        self.target_pos = cell_to_pos(next_cell)
        delta = self.target_pos - self.pos
        dist = delta.length()
        step = speed * dt
        if dist <= step or dist < 0.6:
            self.pos = Vec2(self.target_pos)
            self.cell = next_cell
            self.path.pop(0)
        elif dist > 0:
            self.pos += delta.normalize() * step

    def _ranged_attack(self, game):
        self.state = EnemyState.RANGED
        self.state_lock = 0.34
        self.attack_cooldown = self.attack_interval
        direction = game.player.pos - self.pos
        if direction.length_squared() == 0:
            direction = Vec2(1, 0)
        muzzle = self.pos + direction.normalize() * 18
        game.projectiles.append(Projectile(muzzle, direction, self.bullet_speed, damage=1))
        game.spawn_burst(muzzle, (255, 65, 100), amount=9, speed=55)
        game.shake(0.06, 2)

    def _melee_stab(self, game):
        self.state = EnemyState.MELEE
        self.state_lock = 0.48
        self.melee_cooldown = 1.0
        game.slash_timer = 0.32
        game.damage_player(2, "The thing reached you.")
        game.spawn_burst(game.player.pos, (255, 45, 70), amount=26, speed=170)
        game.shake(0.28, 9)

    def draw(self, surface, assets, offset=(0, 0)):
        surf = assets.enemy_frames.get(self.state, assets.enemy_frames[EnemyState.PATROL])
        bob = int(math.sin(self.anim_t * 10) * 1.5)
        if self.state in (EnemyState.CHASE, EnemyState.RANGED, EnemyState.MELEE):
            glow = pygame.Surface((54, 54), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 25, 64, 35), (27, 27), 25)
            surface.blit(glow, (int(self.pos.x + offset[0] - 27), int(self.pos.y + offset[1] - 27)))
        rect = surf.get_rect(center=(int(self.pos.x + offset[0]), int(self.pos.y + offset[1] + bob)))
        surface.blit(surf, rect)

        if self.state == EnemyState.MELEE:
            slash = pygame.Surface((58, 58), pygame.SRCALPHA)
            pygame.draw.arc(slash, (255, 230, 230, 200), (3, 3, 52, 52), -0.7, 1.1, 4)
            pygame.draw.arc(slash, (255, 55, 85, 180), (9, 8, 42, 42), -0.6, 1.0, 2)
            surface.blit(slash, (int(self.pos.x + offset[0] - 29), int(self.pos.y + offset[1] - 29)))


class SequencePuzzle:
    SYMBOLS = {
        "UP": "↑",
        "DOWN": "↓",
        "LEFT": "←",
        "RIGHT": "→",
    }
    KEYS = {
        pygame.K_UP: "UP", pygame.K_w: "UP",
        pygame.K_DOWN: "DOWN", pygame.K_s: "DOWN",
        pygame.K_LEFT: "LEFT", pygame.K_a: "LEFT",
        pygame.K_RIGHT: "RIGHT", pygame.K_d: "RIGHT",
    }

    def __init__(self, artifact_cell, difficulty):
        self.artifact_cell = artifact_cell
        length = {"Easy": 4, "Normal": 5, "Hard": 6}.get(difficulty, 5)
        self.sequence = [random.choice(list(self.SYMBOLS.keys())) for _ in range(length)]
        self.index = 0
        self.time_limit = {"Easy": 11.0, "Normal": 9.0, "Hard": 7.0}.get(difficulty, 9.0)
        self.time_left = self.time_limit
        self.failed_flash = 0.0
        self.done = False
        self.success = False

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN or self.done:
            return
        if event.key not in self.KEYS:
            return
        pressed = self.KEYS[event.key]
        expected = self.sequence[self.index]
        if pressed == expected:
            self.index += 1
            if self.index >= len(self.sequence):
                self.done = True
                self.success = True
        else:
            self.failed_flash = 0.25
            self.index = max(0, self.index - 1)
            self.time_left -= 1.15
            if self.time_left <= 0:
                self.done = True
                self.success = False

    def update(self, dt):
        self.time_left -= dt
        self.failed_flash = max(0.0, self.failed_flash - dt)
        if self.time_left <= 0 and not self.done:
            self.done = True
            self.success = False

    def draw(self, game, surface):
        dim = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 185))
        surface.blit(dim, (0, 0))

        panel = pygame.Rect(160, 128, WINDOW_W - 320, 440)
        pygame.draw.rect(surface, (5, 7, 12), panel.move(0, 10), border_radius=24)
        panel_color = (42, 17, 28) if self.failed_flash > 0 else Palette.PANEL
        pygame.draw.rect(surface, panel_color, panel, border_radius=24)
        pygame.draw.rect(surface, Palette.ACCENT_2, panel, 2, border_radius=24)

        title_font = game.fonts["title_small"]
        body_font = game.fonts["body"]
        big_font = game.fonts["huge"]
        small_font = game.fonts["small"]

        draw_text(surface, "MEMORY LOCK", title_font, Palette.TEXT, (WINDOW_W // 2, panel.y + 38), "center")
        draw_text(surface, "Repeat the sequence before the artifact devours the memory.", body_font, Palette.MUTED, (WINDOW_W // 2, panel.y + 83), "center")

        # Timer bar
        bar = pygame.Rect(panel.x + 70, panel.y + 115, panel.w - 140, 14)
        pygame.draw.rect(surface, (32, 35, 49), bar, border_radius=7)
        pct = clamp(self.time_left / self.time_limit, 0, 1)
        fill = pygame.Rect(bar.x, bar.y, int(bar.w * pct), bar.h)
        col = Palette.GOOD if pct > 0.55 else Palette.WARNING if pct > 0.27 else Palette.DANGER
        pygame.draw.rect(surface, col, fill, border_radius=7)

        # Sequence blocks
        total_w = len(self.sequence) * 76 - 12
        start_x = WINDOW_W // 2 - total_w // 2
        y = panel.y + 165
        for i, symbol in enumerate(self.sequence):
            rect = pygame.Rect(start_x + i * 76, y, 64, 72)
            if i < self.index:
                color = (32, 98, 78)
                border = Palette.GOOD
            elif i == self.index:
                pulse = (math.sin(pygame.time.get_ticks() * 0.008) + 1) / 2
                color = tuple(int(lerp(a, b, pulse)) for a, b in zip(Palette.PANEL_2, (64, 43, 118)))
                border = Palette.ACCENT_2
            else:
                color = Palette.PANEL_2
                border = Palette.PANEL_3
            pygame.draw.rect(surface, color, rect, border_radius=14)
            pygame.draw.rect(surface, border, rect, 2, border_radius=14)
            draw_text(surface, self.SYMBOLS[symbol], big_font, Palette.TEXT, rect.center, "center")

        draw_text(surface, "Use Arrow Keys or WASD", body_font, Palette.TEXT, (WINDOW_W // 2, panel.y + 300), "center")
        draw_text(surface, "ESC cancels the ritual, but the creature will still be waiting.", small_font, Palette.MUTED, (WINDOW_W // 2, panel.y + 338), "center")


# ------------------------------- MAIN GAME ------------------------------- #


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Shadow Memory - Procedural Horror Puzzle")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.running = True
        self.assets = Assets()
        self.fonts = {
            "huge": make_font(56, True),
            "title": make_font(48, True),
            "title_small": make_font(34, True),
            "button": make_font(24, True),
            "body": make_font(20),
            "small": make_font(15),
            "tiny": make_font(12),
        }
        self.state = State.MENU
        self.difficulty = "Normal"
        self.volume = 70
        self.buttons = {}
        self._make_buttons()

        self.maze = None
        self.player = None
        self.enemy = None
        self.projectiles = []
        self.particles = []
        self.solved_artifacts = set()
        self.fragments = 0
        self.fragments_required = 3
        self.master_key = False
        self.active_puzzle = None
        self.last_noise_cell = None
        self.noise_timer = 0.0
        self.toast_text = ""
        self.toast_timer = 0.0
        self.flash_timer = 0.0
        self.shake_timer = 0.0
        self.shake_power = 0
        self.slash_timer = 0.0
        self.start_time = 0

    def _make_buttons(self):
        cx = WINDOW_W // 2
        self.buttons[State.MENU] = [
            Button((cx - 145, 330, 290, 54), "START GAME", self.start_game, self.fonts.get("button") or make_font(24, True)),
            Button((cx - 145, 400, 290, 54), "OPTIONS", lambda: self.set_state(State.OPTIONS), self.fonts.get("button") or make_font(24, True), Palette.ACCENT_2),
            Button((cx - 145, 470, 290, 54), "QUIT", self.quit, self.fonts.get("button") or make_font(24, True), Palette.DANGER),
        ]
        self.buttons[State.OPTIONS] = [
            Button((cx - 190, 285, 380, 54), "DIFFICULTY: Normal", self.cycle_difficulty, self.fonts.get("button") or make_font(24, True)),
            Button((cx - 190, 355, 380, 54), "VOLUME: 70%", self.cycle_volume, self.fonts.get("button") or make_font(24, True), Palette.ACCENT_2),
            Button((cx - 190, 460, 380, 54), "BACK", lambda: self.set_state(State.MENU), self.fonts.get("button") or make_font(24, True), Palette.WARNING),
        ]
        self.buttons[State.GAME_OVER] = [
            Button((cx - 145, 405, 290, 54), "TRY AGAIN", self.start_game, self.fonts.get("button") or make_font(24, True), Palette.DANGER),
            Button((cx - 145, 475, 290, 54), "MAIN MENU", lambda: self.set_state(State.MENU), self.fonts.get("button") or make_font(24, True)),
        ]
        self.buttons[State.VICTORY] = [
            Button((cx - 145, 430, 290, 54), "NEW MAZE", self.start_game, self.fonts.get("button") or make_font(24, True), Palette.GOOD),
            Button((cx - 145, 500, 290, 54), "MAIN MENU", lambda: self.set_state(State.MENU), self.fonts.get("button") or make_font(24, True)),
        ]

    def refresh_option_labels(self):
        self.buttons[State.OPTIONS][0].text = f"DIFFICULTY: {self.difficulty}"
        self.buttons[State.OPTIONS][1].text = f"VOLUME: {self.volume}%"

    def cycle_difficulty(self):
        order = ["Easy", "Normal", "Hard"]
        self.difficulty = order[(order.index(self.difficulty) + 1) % len(order)]
        self.refresh_option_labels()

    def cycle_volume(self):
        values = [0, 35, 70, 100]
        idx = values.index(self.volume) if self.volume in values else 1
        self.volume = values[(idx + 1) % len(values)]
        self.refresh_option_labels()

    def set_state(self, state):
        self.state = state

    def start_game(self):
        artifact_count = 3
        self.maze = Maze(GRID_W, GRID_H, artifact_count=artifact_count)
        self.player = Player(self.maze.player_start)
        self.enemy = Enemy(self.maze.enemy_start, self.difficulty)
        self.projectiles = []
        self.particles = []
        self.solved_artifacts = set()
        self.fragments = 0
        self.fragments_required = artifact_count
        self.master_key = False
        self.active_puzzle = None
        self.last_noise_cell = None
        self.noise_timer = 0.0
        self.toast_text = "Find the memory fragments. Avoid the thing in the dark."
        self.toast_timer = 3.4
        self.flash_timer = 0.0
        self.shake_timer = 0.0
        self.shake_power = 0
        self.slash_timer = 0.0
        self.start_time = pygame.time.get_ticks()
        self.state = State.GAMEPLAY

    def quit(self):
        self.running = False

    def make_noise(self, cell, strength=1.0):
        self.last_noise_cell = cell
        self.noise_timer = max(self.noise_timer, 0.55 * strength)

    def spawn_burst(self, pos, color, amount=14, speed=90):
        for _ in range(amount):
            angle = random.random() * math.tau
            mag = random.uniform(speed * 0.25, speed)
            vel = Vec2(math.cos(angle), math.sin(angle)) * mag
            c = tuple(clamp(int(v + random.randint(-18, 18)), 0, 255) for v in color)
            self.particles.append(Particle(pos, vel, c, life=random.uniform(0.35, 0.75), size=random.randint(2, 4)))

    def shake(self, seconds, power):
        self.shake_timer = max(self.shake_timer, seconds)
        self.shake_power = max(self.shake_power, power)

    def damage_player(self, amount, message):
        if self.player is None or self.player.invuln > 0 or self.state not in (State.GAMEPLAY, State.PUZZLE_POPUP):
            return
        self.player.hp -= amount
        self.player.invuln = 0.85
        self.flash_timer = 0.28
        self.toast_text = message
        self.toast_timer = 1.7
        self.shake(0.18, 7)
        if self.player.hp <= 0:
            self.player.hp = 0
            self.state = State.GAME_OVER

    def nearby_artifact(self):
        if not self.maze or not self.player:
            return None
        candidates = [self.player.cell]
        x, y = self.player.cell
        candidates.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])
        for cell in candidates:
            if cell in self.maze.artifacts and cell not in self.solved_artifacts:
                return cell
        return None

    def player_near_exit(self):
        if not self.maze or not self.player:
            return False
        return manhattan(self.player.cell, self.maze.exit_cell) <= 1 or self.player.cell == self.maze.exit_cell

    def interact(self):
        artifact = self.nearby_artifact()
        if artifact is not None:
            self.active_puzzle = SequencePuzzle(artifact, self.difficulty)
            self.state = State.PUZZLE_POPUP
            return
        if self.player_near_exit():
            if self.master_key:
                self.spawn_burst(cell_to_pos(self.maze.exit_cell), Palette.GOOD, amount=50, speed=170)
                self.state = State.VICTORY
            else:
                remaining = self.fragments_required - self.fragments
                self.toast_text = f"The exit rejects you. {remaining} fragment{'s' if remaining != 1 else ''} missing."
                self.toast_timer = 2.4
                self.shake(0.08, 3)
            return
        self.toast_text = "Nothing answers."
        self.toast_timer = 1.0

    def resolve_puzzle_if_done(self):
        if not self.active_puzzle or not self.active_puzzle.done:
            return
        puzzle = self.active_puzzle
        if puzzle.success:
            self.solved_artifacts.add(puzzle.artifact_cell)
            self.fragments += 1
            self.spawn_burst(cell_to_pos(puzzle.artifact_cell), (100, 255, 224), amount=42, speed=145)
            if self.fragments >= self.fragments_required:
                self.master_key = True
                self.toast_text = "The Master Key forms from the fragments. Find the exit."
                self.toast_timer = 3.0
            else:
                self.toast_text = f"Memory Fragment recovered: {self.fragments}/{self.fragments_required}"
                self.toast_timer = 2.3
        else:
            self.toast_text = "The memory lock bites back."
            self.toast_timer = 2.0
            self.damage_player(1, "The failed ritual wounded you.")
        self.active_puzzle = None
        if self.player.hp <= 0:
            self.state = State.GAME_OVER
        else:
            self.state = State.GAMEPLAY

    # ----------------------------- EVENT LOOP ----------------------------- #

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                continue

            if self.state in self.buttons:
                for button in self.buttons[self.state]:
                    button.handle_event(event)

            if event.type == pygame.KEYDOWN:
                if self.state == State.GAMEPLAY:
                    if event.key == pygame.K_ESCAPE:
                        self.state = State.MENU
                    elif event.key == pygame.K_e:
                        self.interact()
                elif self.state == State.PUZZLE_POPUP:
                    if event.key == pygame.K_ESCAPE:
                        self.active_puzzle = None
                        self.toast_text = "You stepped away from the artifact."
                        self.toast_timer = 1.5
                        self.state = State.GAMEPLAY
                    elif self.active_puzzle:
                        self.active_puzzle.handle_event(event)
                elif self.state in (State.GAME_OVER, State.VICTORY):
                    if event.key == pygame.K_RETURN:
                        self.start_game()
                    elif event.key == pygame.K_ESCAPE:
                        self.state = State.MENU
                elif self.state == State.MENU:
                    if event.key == pygame.K_RETURN:
                        self.start_game()
                elif self.state == State.OPTIONS and event.key == pygame.K_ESCAPE:
                    self.state = State.MENU

    def update(self, dt):
        for button_list in self.buttons.values():
            for button in button_list:
                button.update(dt)

        self.toast_timer = max(0.0, self.toast_timer - dt)
        self.flash_timer = max(0.0, self.flash_timer - dt)
        self.shake_timer = max(0.0, self.shake_timer - dt)
        if self.shake_timer <= 0:
            self.shake_power = 0
        self.slash_timer = max(0.0, self.slash_timer - dt)

        if self.state == State.GAMEPLAY:
            self.noise_timer = max(0.0, self.noise_timer - dt)
            self.player.update(self, dt)
            self.enemy.update(self, dt)
            self.projectiles = [p for p in self.projectiles if p.update(self, dt)]
            self.particles = [p for p in self.particles if p.update(dt)]
        elif self.state == State.PUZZLE_POPUP:
            if self.active_puzzle:
                self.active_puzzle.update(dt)
                self.resolve_puzzle_if_done()
            # Give particles tiny life even in popup so the screen feels alive.
            self.particles = [p for p in self.particles if p.update(dt * 0.25)]
        else:
            self.particles = [p for p in self.particles if p.update(dt)]

    # ------------------------------- DRAWING ------------------------------ #

    def current_shake_offset(self):
        if self.shake_timer <= 0 or self.shake_power <= 0:
            return (0, 0)
        power = self.shake_power * clamp(self.shake_timer / 0.28, 0.25, 1.0)
        return (random.randint(-int(power), int(power)), random.randint(-int(power), int(power)))

    def draw(self):
        self.screen.fill(Palette.BG)
        if self.state == State.MENU:
            self.draw_menu()
        elif self.state == State.OPTIONS:
            self.draw_options()
        elif self.state in (State.GAMEPLAY, State.PUZZLE_POPUP):
            self.draw_gameplay()
            if self.state == State.PUZZLE_POPUP and self.active_puzzle:
                self.active_puzzle.draw(self, self.screen)
        elif self.state == State.GAME_OVER:
            self.draw_gameplay(frozen=True)
            self.draw_game_over()
        elif self.state == State.VICTORY:
            self.draw_gameplay(frozen=True)
            self.draw_victory()
        pygame.display.flip()

    def draw_background_grid(self):
        for y in range(0, WINDOW_H, 32):
            pygame.draw.line(self.screen, (10, 13, 22), (0, y), (WINDOW_W, y))
        for x in range(0, WINDOW_W, 32):
            pygame.draw.line(self.screen, (10, 13, 22), (x, 0), (x, WINDOW_H))

    def draw_menu(self):
        self.draw_background_grid()
        ticks = pygame.time.get_ticks() * 0.001
        glow = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        pygame.draw.circle(glow, (90, 65, 255, 30), (WINDOW_W // 2, 205), 190)
        pygame.draw.circle(glow, (255, 40, 85, 18), (WINDOW_W // 2 - 155, 280), 120)
        self.screen.blit(glow, (0, 0))
        title_y = 145 + int(math.sin(ticks * 2.1) * 4)
        draw_text(self.screen, "SHADOW MEMORY", self.fonts["title"], Palette.TEXT, (WINDOW_W // 2, title_y), "center")
        draw_text(self.screen, "A procedural top-down horror puzzle", self.fonts["body"], Palette.MUTED, (WINDOW_W // 2, title_y + 54), "center")
        draw_text(self.screen, "Generated sprites • A* hunter • Fog of war • Memory puzzles", self.fonts["small"], Palette.ACCENT_2, (WINDOW_W // 2, title_y + 88), "center")
        for button in self.buttons[State.MENU]:
            button.draw(self.screen)
        draw_text(self.screen, "ENTER starts quickly   |   E interacts in-game", self.fonts["tiny"], Palette.MUTED, (WINDOW_W // 2, WINDOW_H - 34), "center")

    def draw_options(self):
        self.draw_background_grid()
        panel = pygame.Rect(215, 130, 530, 460)
        pygame.draw.rect(self.screen, (0, 0, 0), panel.move(0, 8), border_radius=26)
        pygame.draw.rect(self.screen, Palette.PANEL, panel, border_radius=26)
        pygame.draw.rect(self.screen, Palette.ACCENT_2, panel, 2, border_radius=26)
        draw_text(self.screen, "OPTIONS", self.fonts["title_small"], Palette.TEXT, (WINDOW_W // 2, 185), "center")
        draw_text(self.screen, "Difficulty changes enemy speed, hearing, and attack rhythm.", self.fonts["small"], Palette.MUTED, (WINDOW_W // 2, 230), "center")
        draw_text(self.screen, "Volume is a ready UI setting; this build uses visual-only procedural polish.", self.fonts["small"], Palette.MUTED, (WINDOW_W // 2, 252), "center")
        for button in self.buttons[State.OPTIONS]:
            button.draw(self.screen)

    def draw_gameplay(self, frozen=False):
        if not self.maze:
            self.start_game()
        offset = self.current_shake_offset()
        self.draw_world(offset)
        self.draw_lighting(offset)
        self.draw_hud()
        self.draw_toast()
        if self.flash_timer > 0:
            alpha = int(130 * clamp(self.flash_timer / 0.28, 0, 1))
            flash = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            flash.fill((255, 0, 32, alpha))
            self.screen.blit(flash, (0, 0))

    def draw_world(self, offset):
        # Deep frame around map.
        pygame.draw.rect(self.screen, (2, 3, 7), (GRID_X - 8 + offset[0], GRID_Y - 8 + offset[1], WORLD_W + 16, WORLD_H + 16), border_radius=8)
        for y in range(self.maze.h):
            for x in range(self.maze.w):
                dest = (GRID_X + x * TILE + offset[0], GRID_Y + y * TILE + offset[1])
                if self.maze.grid[y][x] == 1:
                    idx = (x * 17 + y * 31) % len(self.assets.wall_tiles)
                    self.screen.blit(self.assets.wall_tiles[idx], dest)
                else:
                    idx = (x * 13 + y * 7) % len(self.assets.floor_tiles)
                    self.screen.blit(self.assets.floor_tiles[idx], dest)

        # Exit glow + door
        exit_pos = cell_to_pos(self.maze.exit_cell)
        glow = pygame.Surface((96, 96), pygame.SRCALPHA)
        glow_color = (89, 214, 255, 45) if self.master_key else (224, 48, 78, 34)
        pygame.draw.circle(glow, glow_color, (48, 48), 42)
        self.screen.blit(glow, (int(exit_pos.x + offset[0] - 48), int(exit_pos.y + offset[1] - 48)))
        exit_surf = self.assets.exit_unlocked if self.master_key else self.assets.exit_locked
        self.screen.blit(exit_surf, exit_surf.get_rect(center=(int(exit_pos.x + offset[0]), int(exit_pos.y + offset[1]))))

        # Artifacts
        ticks = pygame.time.get_ticks() * 0.001
        for cell in self.maze.artifacts:
            if cell in self.solved_artifacts:
                continue
            pos = cell_to_pos(cell)
            pulse = (math.sin(ticks * 4 + cell[0]) + 1) / 2
            glow = pygame.Surface((80, 80), pygame.SRCALPHA)
            pygame.draw.circle(glow, (80, 255, 230, int(25 + 30 * pulse)), (40, 40), int(26 + 3 * pulse))
            self.screen.blit(glow, (int(pos.x + offset[0] - 40), int(pos.y + offset[1] - 40)))
            bob = int(math.sin(ticks * 5 + cell[1]) * 2)
            rect = self.assets.artifact.get_rect(center=(int(pos.x + offset[0]), int(pos.y + offset[1] + bob)))
            self.screen.blit(self.assets.artifact, rect)

        # Entities and projectiles
        for projectile in self.projectiles:
            projectile.draw(self.screen, self.assets, offset)
        self.enemy.draw(self.screen, self.assets, offset)
        self.player.draw(self.screen, self.assets, offset)

        if self.slash_timer > 0:
            ring = pygame.Surface((90, 90), pygame.SRCALPHA)
            alpha = int(190 * clamp(self.slash_timer / 0.32, 0, 1))
            pygame.draw.arc(ring, (255, 230, 235, alpha), (6, 6, 78, 78), 0.1, 2.6, 5)
            self.screen.blit(ring, (int(self.player.pos.x + offset[0] - 45), int(self.player.pos.y + offset[1] - 45)))

        for particle in self.particles:
            particle.draw(self.screen, offset)

        # Interaction prompt
        prompt = None
        if self.nearby_artifact() is not None:
            prompt = "E  Decode Artifact"
        elif self.player_near_exit():
            prompt = "E  Unlock Exit" if self.master_key else "Exit locked: fragments required"
        if prompt:
            pos = self.player.pos + Vec2(0, -36)
            rect = pygame.Rect(0, 0, 210, 28)
            rect.center = (int(pos.x + offset[0]), int(pos.y + offset[1]))
            pygame.draw.rect(self.screen, (0, 0, 0), rect.inflate(4, 4), border_radius=9)
            pygame.draw.rect(self.screen, Palette.PANEL_2, rect, border_radius=9)
            pygame.draw.rect(self.screen, Palette.ACCENT_2, rect, 1, border_radius=9)
            draw_text(self.screen, prompt, self.fonts["tiny"], Palette.TEXT, rect.center, "center")

    def draw_lighting(self, offset):
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 238))
        light = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        cx = int(self.player.pos.x + offset[0])
        cy = int(self.player.pos.y + offset[1])

        # Radial lantern/flashlight falloff: subtract alpha from the black overlay.
        pygame.draw.circle(light, (0, 0, 0, 230), (cx, cy), 62)
        pygame.draw.circle(light, (0, 0, 0, 168), (cx, cy), 112)
        pygame.draw.circle(light, (0, 0, 0, 95), (cx, cy), 165)
        pygame.draw.circle(light, (0, 0, 0, 42), (cx, cy), 230)

        # Directional cone based on last movement direction.
        direction = Vec2(self.player.direction)
        if direction.length_squared() > 0:
            direction = direction.normalize()
            perp = Vec2(-direction.y, direction.x)
            tip = Vec2(cx, cy) + direction * 260
            left = Vec2(cx, cy) + perp * 74 + direction * 28
            right = Vec2(cx, cy) - perp * 74 + direction * 28
            pygame.draw.polygon(light, (0, 0, 0, 82), [left, tip, right])
            pygame.draw.circle(light, (0, 0, 0, 120), (int(tip.x), int(tip.y)), 44)

        overlay.blit(light, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        self.screen.blit(overlay, (0, 0))

    def draw_hud(self):
        hud = pygame.Rect(0, 0, WINDOW_W, HUD_H)
        pygame.draw.rect(self.screen, (5, 7, 12), hud)
        pygame.draw.rect(self.screen, (20, 24, 38), (0, HUD_H - 2, WINDOW_W, 2))
        draw_text(self.screen, "SHADOW MEMORY", self.fonts["body"], Palette.TEXT, (18, 16), "topleft")
        draw_text(self.screen, f"AI: {self.enemy.state}", self.fonts["tiny"], Palette.MUTED, (18, 43), "topleft")

        # Segmented health
        x0 = 300
        draw_text(self.screen, "HP", self.fonts["small"], Palette.MUTED, (x0, 16), "topleft")
        for i in range(self.player.max_hp):
            rect = pygame.Rect(x0 + 36 + i * 38, 15, 28, 22)
            pygame.draw.rect(self.screen, (32, 35, 49), rect, border_radius=6)
            if i < self.player.hp:
                pygame.draw.rect(self.screen, Palette.DANGER, rect.inflate(-4, -4), border_radius=5)
            pygame.draw.rect(self.screen, (65, 72, 96), rect, 1, border_radius=6)

        # Fragments / key
        fx = 510
        self.screen.blit(self.assets.fragment_icon, (fx, 15))
        draw_text(self.screen, f"{self.fragments}/{self.fragments_required}", self.fonts["body"], Palette.TEXT, (fx + 30, 14), "topleft")
        self.screen.blit(self.assets.key_icon, (fx + 105, 14))
        key_text = "MASTER KEY" if self.master_key else "LOCKED"
        key_col = Palette.GOOD if self.master_key else Palette.MUTED
        draw_text(self.screen, key_text, self.fonts["small"], key_col, (fx + 135, 18), "topleft")

        # Time survived
        elapsed = 0 if self.start_time == 0 else (pygame.time.get_ticks() - self.start_time) // 1000
        mins, secs = divmod(elapsed, 60)
        draw_text(self.screen, f"{mins:02d}:{secs:02d}", self.fonts["body"], Palette.ACCENT_2, (WINDOW_W - 92, 16), "topleft")
        draw_text(self.screen, "E interact  |  ESC menu", self.fonts["tiny"], Palette.MUTED, (WINDOW_W - 204, 45), "topleft")

    def draw_toast(self):
        if self.toast_timer <= 0 or not self.toast_text:
            return
        alpha = int(220 * clamp(self.toast_timer / 0.35, 0, 1)) if self.toast_timer < 0.35 else 220
        text_img = self.fonts["small"].render(self.toast_text, True, Palette.TEXT)
        rect = text_img.get_rect(center=(WINDOW_W // 2, WINDOW_H - 37))
        bg = rect.inflate(34, 18)
        tmp = pygame.Surface(bg.size, pygame.SRCALPHA)
        pygame.draw.rect(tmp, (9, 12, 20, alpha), tmp.get_rect(), border_radius=12)
        pygame.draw.rect(tmp, (*Palette.ACCENT_2, min(255, alpha)), tmp.get_rect(), 1, border_radius=12)
        self.screen.blit(tmp, bg)
        text_img.set_alpha(alpha)
        self.screen.blit(text_img, rect)

    def draw_game_over(self):
        dim = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 190))
        self.screen.blit(dim, (0, 0))
        panel = pygame.Rect(215, 175, 530, 390)
        pygame.draw.rect(self.screen, (0, 0, 0), panel.move(0, 9), border_radius=28)
        pygame.draw.rect(self.screen, (26, 8, 17), panel, border_radius=28)
        pygame.draw.rect(self.screen, Palette.DANGER, panel, 2, border_radius=28)
        draw_text(self.screen, "YOU WERE FORGOTTEN", self.fonts["title_small"], Palette.TEXT, (WINDOW_W // 2, 245), "center")
        draw_text(self.screen, "The hunter wrote your name into the walls.", self.fonts["body"], Palette.MUTED, (WINDOW_W // 2, 292), "center")
        draw_text(self.screen, f"Fragments recovered: {self.fragments}/{self.fragments_required}", self.fonts["small"], Palette.TEXT, (WINDOW_W // 2, 330), "center")
        for button in self.buttons[State.GAME_OVER]:
            button.draw(self.screen)

    def draw_victory(self):
        dim = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 170))
        self.screen.blit(dim, (0, 0))
        panel = pygame.Rect(195, 158, 570, 430)
        pygame.draw.rect(self.screen, (0, 0, 0), panel.move(0, 9), border_radius=28)
        pygame.draw.rect(self.screen, (8, 25, 29), panel, border_radius=28)
        pygame.draw.rect(self.screen, Palette.GOOD, panel, 2, border_radius=28)
        draw_text(self.screen, "THE DOOR OPENS", self.fonts["title_small"], Palette.TEXT, (WINDOW_W // 2, 238), "center")
        draw_text(self.screen, "You escaped with the fragments of yourself intact.", self.fonts["body"], Palette.MUTED, (WINDOW_W // 2, 286), "center")
        elapsed = 0 if self.start_time == 0 else (pygame.time.get_ticks() - self.start_time) // 1000
        mins, secs = divmod(elapsed, 60)
        draw_text(self.screen, f"Escape time: {mins:02d}:{secs:02d}", self.fonts["small"], Palette.ACCENT_2, (WINDOW_W // 2, 326), "center")
        for button in self.buttons[State.VICTORY]:
            button.draw(self.screen)

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 1 / 20)  # Avoid giant simulation jumps after window drag.
            self.handle_events()
            self.update(dt)
            self.draw()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()
