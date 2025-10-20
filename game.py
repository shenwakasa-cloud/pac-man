"""
pacman_classic.py
A single-file classic-style Pac-Man clone in pygame.
Features:
- Classic 28x31 tile maze (map defined as text)
- Pellets and power pellets
- 4 ghosts with grid pathfinding (BFS-based) and simple scatter/chase behavior
- Score, lives, READY state, Game Over and Restart
- No external assets required (drawn shapes)

Requirements: pygame (tested with pygame 2.x)
Run: python3 pacman_classic.py
"""

import pygame, sys, random, collections, time, math

# --- Config ---
TILE = 16            # tile size in pixels (classic: 16)
COLS = 28
ROWS = 31
WIDTH = COLS * TILE
HEIGHT = ROWS * TILE
FPS = 60

PLAYER_SPEED = 5.0   # tiles per second (movement in grid steps per second)
GHOST_SPEED = 4.0    # tiles per second (normal)
FRIGHT_SPEED = 2.5   # when frightened
POWER_DURATION = 8.0 # seconds ghosts remain frightened

# Colors
BLACK = (0,0,0)
NAVY = (0, 0, 0)
WALL_BLUE = (0, 50, 200)
PELLET_COLOR = (240, 220, 0)
POWER_COLOR = (255, 255, 255)
TEXT_COLOR = (255, 255, 255)
SCORE_COLOR = (255, 255, 255)
PLAYER_COLOR = (255, 220, 0)
GHOST_COLORS = {
    "blinky": (255,0,0),
    "pinky": (255,184,255),
    "inky": (0,255,255),
    "clyde": (255,184,82),
}


# map legend:
# '#' = wall
# '.' = pellet
# 'o' = power pellet
# ' ' = empty path
# 'P' = player start
# 'B' = ghost box / block
# '1','2','3','4' = ghost start positions (Blinky, Pinky, Inky, Clyde)
MAP = [
"############ ###############",
"#............##............#",
"#.####.#####.##.#####.####.#",
"#o####.#####.##.#####.####o#",
"#.####.#####.##.#####.####.#",
"#..........................#",
"#.####.##.########.##.####.#",
"#.####.##.########.##.####.#",
"#......##....##....##......#",
"######.##### ## #####.######",
"     #.##### ## #####.#     ",
"     #.##          ##.#     ",
"     #.## ###--### ##.#     ",
"######.## #      # ##.######",
"      .   # B  B #   .      ",
"######.## #      # ##.######",
"     #.## ######## ##.#     ",
"     #.##          ##.#     ",
"     #.## ######## ##.#     ",
"######.## #......# ##.######",
"#............##............#",
"#.####.#####.##.#####.####.#",
"#.####.#####.##.#####.####.#",
"#o..##................##..o#",
"###.##.##.########.##.##.###",
"###.##.##.########.##.##.###",
"#......##....##....##......#",
"#.##########.##.##########.#",
"#.#####   ##.##.##   #####.#",
"#..........................#",
"############ ###############"
]

# Replace spaces in map row 10-18 due to arcade center spacing: we keep map width 28 per row
# Some rows have leading spaces in the original text; ensure all rows are 28 chars:
MAP = [row.ljust(COLS)[:COLS] for row in MAP]

# Helper grid functions
def in_bounds(r,c):
    return 0 <= r < ROWS and 0 <= c < COLS

def is_wall(tile):
    return tile == '#'

def neighbors(rc):
    r,c = rc
    for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
        nr, nc = r+dr, c+dc
        if in_bounds(nr,nc) and not is_wall(MAP[nr][nc]):
            yield (nr,nc)

# Convert to tile grid for pathfinding and initial placements
pellets = set()
power_pellets = set()
player_start = None
ghost_starts = {}
for r,row in enumerate(MAP):
    for c,ch in enumerate(row):
        if ch == '.':
            pellets.add((r,c))
        elif ch == 'o':
            power_pellets.add((r,c))
        elif ch == 'P':
            player_start = (r,c)
        elif ch in '1234':
            ghost_starts[ch] = (r,c)
        # treat spaces and 'B' as walkable (B will be drawn as box)
        # walls (#) are not walkable

# If player_start not set, put player near bottom center (classic)
if not player_start:
    # find a free tile near bottom center
    for r in range(ROWS-1, -1, -1):
        for c in range(COLS//2-3, COLS//2+3):
            if MAP[r][c] in (' ', '.', 'o'):
                player_start = (r,c)
                break
        if player_start: break

# Ghost default starts if none provided
if not ghost_starts:
    ghost_starts = {
        '1': (13,13),
        '2': (13,14),
        '3': (13,12),
        '4': (13,15)
    }

# BFS pathfinder on grid (returns list of tile positions from start to goal)
def bfs(start, goal):
    if start == goal: return [start]
    q = collections.deque([start])
    came = {start: None}
    while q:
        cur = q.popleft()
        for n in neighbors(cur):
            if n not in came:
                came[n] = cur
                if n == goal:
                    # build path
                    path = [n]
                    while cur is not None:
                        path.append(cur)
                        cur = came[cur]
                    return path[::-1]
                q.append(n)
    return None

# Convert tile center -> pixel
def tile_center(tile):
    r,c = tile
    return (c * TILE + TILE//2, r * TILE + TILE//2)

# Movement helpers (tile-based movement with sub-tile smoothness)
def lerp(a,b,t): return a + (b-a)*t

# --- Entities ---
class Player:
    def __init__(self, start_tile):
        self.tile = start_tile
        self.pos = pygame.Vector2(tile_center(start_tile))
        self.dir = pygame.Vector2(0,0)   # direction in tiles (dx,dy)
        self.next_dir = pygame.Vector2(0,0)
        self.radius = TILE//2 - 1
        self.lives = 3
        self.score = 0
        self.alive = True

    def update(self, dt):
        # dt in seconds, movement in pixels
        # convert directions to (dr,dc)
        if self.next_dir.length_squared() > 0:
            # attempt to turn if possible (tile-aligned turns)
            nd = (int(self.next_dir.y), int(self.next_dir.x))
            # check if next tile is free
            r,c = self.tile
            tr,tc = r + nd[0], c + nd[1]
            if in_bounds(tr,tc) and not is_wall(MAP[tr][tc]):
                self.dir = self.next_dir

        # attempt to move
        move_pixels = PLAYER_SPEED * TILE * dt
        if self.dir.length_squared() == 0:
            return

        # compute desired pixel target
        dir_tile = (int(self.dir.y), int(self.dir.x))
        target_tile = (self.tile[0] + dir_tile[0], self.tile[1] + dir_tile[1])
        if not in_bounds(*target_tile) or is_wall(MAP[target_tile[0]][target_tile[1]]):
            # blocked, stop
            return

        target_pos = pygame.Vector2(tile_center(target_tile))
        # move towards target_pos
        to_target = target_pos - self.pos
        dist = to_target.length()
        if dist <= move_pixels:
            # snap to target tile
            self.pos = target_pos
            self.tile = target_tile
        else:
            self.pos += to_target.normalize() * move_pixels

    def draw(self, surf):
        x,y = int(self.pos.x), int(self.pos.y)
        # Pac-Man mouth animation based on time
        t = pygame.time.get_ticks() / 150.0
        mouth = 0.25 + 0.25 * math.sin(t)
        # direction angle
        if self.dir.length_squared() > 0:
            ang = math.degrees(math.atan2(-self.dir.y, self.dir.x))
        else:
            ang = 0
        # draw circle and mouth triangle
        pygame.draw.circle(surf, PLAYER_COLOR, (x,y), self.radius)
        a = math.radians(ang)
        a1 = a - mouth * math.pi
        a2 = a + mouth * math.pi
        p1 = (x + int(math.cos(a1)*self.radius), y + int(math.sin(a1)*self.radius))
        p2 = (x + int(math.cos(a2)*self.radius), y + int(math.sin(a2)*self.radius))
        pygame.draw.polygon(surf, BLACK, [(x,y), p1, p2])

class Ghost:
    def __init__(self, name, start_tile, scatter_target):
        self.name = name
        self.tile = start_tile
        self.pos = pygame.Vector2(tile_center(start_tile))
        self.radius = TILE//2 - 1
        self.color = GHOST_COLORS.get(name, (200,100,200))
        self.mode = "scatter"  # scatter, chase, frightened, eaten
        self.scatter_target = scatter_target
        self.target = scatter_target
        self.path = []
        self.path_index = 0
        self.speed = GHOST_SPEED
        self.fright_timer = 0.0

    def set_fright(self):
        if self.mode != "eaten":
            self.mode = "frightened"
            self.fright_timer = POWER_DURATION

    def update(self, dt, player_tile, player_pos, grid):
        # Mode handling
        if self.mode == "frightened":
            self.fright_timer -= dt
            if self.fright_timer <= 0:
                self.mode = "chase"
        # Decide target tile
        if self.mode == "scatter":
            self.target = self.scatter_target
        elif self.mode == "chase":
            self.target = player_tile
        elif self.mode == "frightened":
            # random wander target
            self.target = random.choice([ (random.randint(0,ROWS-1), random.randint(0,COLS-1)) ])
        elif self.mode == "eaten":
            # go to ghost box (home) - use scatter_target as home entrance
            self.target = (13,13)

        # Recompute path occasionally or if finished
        recalc = False
        if not self.path or self.path_index >= len(self.path):
            recalc = True
        else:
            # if target changed tile, recalc
            if self.path and self.path[-1] != self.target:
                recalc = True

        if recalc:
            start = (int(round(self.pos.y / TILE)), int(round(self.pos.x / TILE)))
            p = bfs(start, self.target)
            if p:
                self.path = p
                # path[0] is start tile, we want to step to next tile
                self.path_index = 1 if len(p) > 1 else 0

        # move along path
        move_pixels = (FRIGHT_SPEED if self.mode == "frightened" else self.speed) * TILE * dt
        if self.path and self.path_index < len(self.path):
            next_tile = self.path[self.path_index]
            target_pos = pygame.Vector2(tile_center(next_tile))
            to_target = target_pos - self.pos
            dist = to_target.length()
            if dist <= move_pixels or dist == 0:
                # snap to tile
                self.pos = target_pos
                self.tile = next_tile
                self.path_index += 1
            else:
                self.pos += to_target.normalize() * move_pixels

    def draw(self, surf):
        x,y = int(self.pos.x), int(self.pos.y)
        if self.mode == "frightened":
            # blue frightened ghost
            body_col = (50,50,255)
        elif self.mode == "eaten":
            # eyes only (draw white eyes)
            pygame.draw.circle(surf, (255,255,255), (x-6,y-4), 3)
            pygame.draw.circle(surf, (255,255,255), (x+6,y-4), 3)
            pygame.draw.circle(surf, (0,0,0), (x-6,y-4), 1)
            pygame.draw.circle(surf, (0,0,0), (x+6,y-4), 1)
            return
        else:
            body_col = self.color

        # simple ghost body (circle + rectangle)
        pygame.draw.rect(surf, body_col, (x-self.radius, y-self.radius+4, self.radius*2, self.radius+6))
        pygame.draw.circle(surf, body_col, (x-self.radius+6, y-self.radius+4), self.radius)
        pygame.draw.circle(surf, body_col, (x+self.radius-6, y-self.radius+4), self.radius)
        # eyes
        pygame.draw.circle(surf, (255,255,255), (x-6, y-2), 3)
        pygame.draw.circle(surf, (255,255,255), (x+6, y-2), 3)
        pygame.draw.circle(surf, (0,0,255), (x-6+ (1 if self.mode!='frightened' else 0), y-2), 1)
        pygame.draw.circle(surf, (0,0,255), (x+6+ (1 if self.mode!='frightened' else 0), y-2), 1)

# --- Game init ---
pygame.init()
pygame.mixer.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Mini Classic Pac-Man")
clock = pygame.time.Clock()
font = pygame.font.SysFont("arial", 18)
bigfont = pygame.font.SysFont("arial", 36, bold=True)
main_bg = pygame.mixer.Sound("./bg.mp3")
main_bg.set_volume(0.5)

# create player and ghosts
player = Player(player_start)
ghosts = [
    Ghost("blinky", ghost_starts.get('1', (13,13)), (0, COLS-2)),      # top-right scatter
    Ghost("pinky", ghost_starts.get('2', (13,14)), (0,1)),            # top-left scatter
    Ghost("inky", ghost_starts.get('3', (13,12)), (ROWS-1, COLS-2)),  # bottom-right scatter
    Ghost("clyde", ghost_starts.get('4', (13,15)), (ROWS-1,1)),       # bottom-left scatter
]

# initial pellets: ensure pellets exist where map has '.'
# (we already collected pellets and power_pellets sets earlier)
pellets_active = set(pellets)
power_active = set(power_pellets)

game_state = "ready"  # ready, playing, gameover
ready_timer = 2.0
power_timer = 0.0
ghost_frightened_until = 0.0

last_time = time.time()

# small helper: tile at pixel position
def pixel_to_tile(px, py):
    return (int(py // TILE), int(px // TILE))

# clamp pos inside map (warp tunnels not implemented)
def clamp_pos(pos):
    x = clamp = pos.x
    # not necessary in this simple implementation

# main loop
running = True
while running:
    main_bg.play()
    dt = clock.tick(FPS) / 1000.0
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            running = False
        elif ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                running = False
            if game_state == "gameover":
                if ev.key == pygame.K_r:
                    # restart full game
                    player = Player(player_start)
                    pellets_active = set(pellets)
                    power_active = set(power_pellets)
                    for g, name in zip(ghosts, ["blinky","pinky","inky","clyde"]):
                        g.tile = ghost_starts.get(str(["1","2","3","4"].index(name)+1), g.tile)
                        g.pos = pygame.Vector2(tile_center(g.tile))
                        g.mode = "scatter"
                    game_state = "ready"
                    ready_timer = 2.0
            else:
                # player direction controls (tile-based)
                if ev.key == pygame.K_LEFT:
                    player.next_dir = pygame.Vector2(-1,0)
                elif ev.key == pygame.K_RIGHT:
                    player.next_dir = pygame.Vector2(1,0)
                elif ev.key == pygame.K_UP:
                    player.next_dir = pygame.Vector2(0,-1)
                elif ev.key == pygame.K_DOWN:
                    player.next_dir = pygame.Vector2(0,1)
                elif ev.key == pygame.K_r and game_state == "ready":
                    # start playing
                    game_state = "playing"
                # if playing pressing R does nothing

    if game_state == "ready":
        ready_timer -= dt
        if ready_timer <= 0:
            game_state = "playing"
    elif game_state == "playing":
        # update player
        player.update(dt)
        # pellet pickup
        ptile = (int(player.tile[0]), int(player.tile[1]))
        if ptile in pellets_active:
            pellets_active.remove(ptile)
            player.score += 10
        if ptile in power_active:
            power_active.remove(ptile)
            player.score += 50
            # set ghosts frightened
            for g in ghosts:
                g.set_fright()
            ghost_frightened_until = time.time() + POWER_DURATION

        # update ghosts
        for g in ghosts:
            # if frightened time expired
            if time.time() > ghost_frightened_until and g.mode == "frightened":
                g.mode = "chase"
            # simple mode toggling between scatter and chase every 7 seconds (basic)
            cycle = int(time.time() // 7) % 2
            if g.mode not in ("frightened","eaten"):
                g.mode = "scatter" if cycle == 0 else "chase"
            # update with pathfinding
            g.update(dt, player.tile, player.pos, MAP)

        # check collisions: player vs ghost
        for g in ghosts:
            dist = (g.pos - player.pos).length()
            if dist < (g.radius + player.radius - 3):
                # collision
                if g.mode == "frightened":
                    # eat ghost
                    g.mode = "eaten"
                    player.score += 200
                    # send to home
                    g.path = []
                    g.path_index = 0
                elif g.mode != "eaten":
                    # player dies
                    player.lives -= 1
                    if player.lives <= 0:
                        game_state = "gameover"
                    else:
                        # reset positions to start
                        player.pos = pygame.Vector2(tile_center(player_start))
                        player.tile = player_start
                        player.dir = pygame.Vector2(0,0)
                        for gh in ghosts:
                            gh.pos = pygame.Vector2(tile_center(gh.tile))
                            gh.path = []
                            gh.mode = "scatter"
                        game_state = "ready"
                        ready_timer = 1.5
                    break

        # win condition (no pellets)
        if not pellets_active and not power_active:
            # simple win: reset pellets and continue
            pellets_active = set(pellets)
            power_active = set(power_pellets)

    # --- Drawing ---
    screen.fill(BLACK)

    # draw maze walls and pellets
    for r,row in enumerate(MAP):
        for c,ch in enumerate(row):
            x = c * TILE
            y = r * TILE
            if ch == '#':
                # draw wall block (outline to look maze-ish)
                pygame.draw.rect(screen, WALL_BLUE, (x, y, TILE, TILE))
                pygame.draw.rect(screen, (0,0,0), (x+2, y+2, TILE-4, TILE-4))
            else:
                # floor; draw pellet if active
                if (r,c) in pellets_active:
                    cx,cy = tile_center((r,c))
                    pygame.draw.circle(screen, PELLET_COLOR, (cx,cy), 2)
                if (r,c) in power_active:
                    cx,cy = tile_center((r,c))
                    pygame.draw.circle(screen, POWER_COLOR, (cx,cy), 5)

    # draw ghosts
    for g in ghosts:
        g.draw(screen)

    # draw player
    player.draw(screen)

    # HUD
    score_surf = font.render(f"Score: {player.score}", True, SCORE_COLOR)
    lives_surf = font.render("Lives: " + " ".join("◉" for _ in range(player.lives)), True, SCORE_COLOR)
    screen.blit(score_surf, (6, 6))
    screen.blit(lives_surf, (WIDTH - lives_surf.get_width() - 6, 6))

    if game_state == "ready":
        text = bigfont.render("READY!", True, (255, 240, 0))
        screen.blit(text, (WIDTH//2 - text.get_width()//2, HEIGHT//2 - 20))
    elif game_state == "gameover":
        gtext = bigfont.render("GAME OVER", True, (240, 100, 100))
        sub = font.render("Press R to restart or ESC to quit", True, TEXT_COLOR)
        screen.blit(gtext, (WIDTH//2 - gtext.get_width()//2, HEIGHT//2 - 36))
        screen.blit(sub, (WIDTH//2 - sub.get_width()//2, HEIGHT//2 + 8))

    pygame.display.flip()

pygame.quit()
sys.exit()

