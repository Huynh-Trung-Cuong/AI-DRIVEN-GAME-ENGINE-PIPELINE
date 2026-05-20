from ursina import *
import random
import sys
import os

try:
    from player import Player1, Player2, action_queue, check_world_collision
except ImportError as e:
    print(f"Lỗi load nhân vật: {e}")
    sys.exit(1)

app = Ursina()

# --- CAMERA ---
camera.orthographic = True
camera.fov = 40
camera.position = (0, 40, -25)
camera.look_at(Vec3(0, 0, 0))

def resolve_stuck(player):
    """Đẩy nhân vật ra khỏi địa hình nếu bị kẹt bên trong"""
    if not check_world_collision(player.position, player.position, player.scale, [player]):
        return

    push_dist = 0.2
    directions = [Vec3(1,0,0), Vec3(-1,0,0), Vec3(0,0,1), Vec3(0,0,-1)]

    for i in range(1, 10):
        for d in directions:
            test_pos = player.position + d * push_dist * i
            if not check_world_collision(test_pos, test_pos, player.scale, [player]):
                player.position = test_pos
                return

# --- ATTACK SYSTEM (Centralized) ---
# Logic Projectile đã được chuyển ra file combat.py để tránh lỗi vòng lặp và dễ quản lý.

def handle_player_attack(player):
    if player.sm.current_state in ["IDLE", "MOVE"]:
        if player.sm.request_transition("ATTACK"):
            # Sử dụng logic tấn công đặc trưng của từng nhân vật
            player.execute_attack()
            # Quay lại IDLE sau 0.3s
            invoke(player.sm.request_transition, 'IDLE', delay=0.3)

def handle_player_skill1(player):
    if hasattr(player, 'execute_skill1'):
        player.execute_skill1()

def handle_player_skill2(player):
    if hasattr(player, 'execute_skill2'):
        player.execute_skill2()

# --- MOVEMENT SYSTEM ---
def handle_player_movement(player):
    can_move = (player.sm.current_state in ["IDLE", "MOVE"]) or getattr(player, 'allow_movement', False)
    if not can_move:
        return

    move_dir = Vec3(
        held_keys[player.controls['right']] - held_keys[player.controls['left']],
        0,
        held_keys[player.controls['up']] - held_keys[player.controls['down']]
    )

    if move_dir.length() > 0:
        move_dir = move_dir.normalized()
        player.direction = move_dir
        target_rot = math.degrees(math.atan2(move_dir.x, move_dir.z))
        player.rotation_y = lerp(player.rotation_y, target_rot, time.dt * 50)
        final_move = move_dir * player.move_speed * time.dt

        old_pos = Vec3(player.position)
        new_pos = player.position + final_move
        if not check_world_collision(old_pos, new_pos, player.scale, [player]):
            player.position = new_pos

        if player.sm.current_state in ["IDLE", "MOVE"]:
            player.sm.request_transition("MOVE")
    else:
        if player.sm.current_state == "MOVE":
            player.sm.request_transition("IDLE")

    resolve_stuck(player)

# --- MAP & ĐỊA HÌNH ---
map_size = 35
ground = Entity(model='cube', color=color.dark_gray, scale=(map_size, 1, map_size), position=(0, -0.5, 0), collider='box', is_ground=True)

wall_thickness = 2
wall_height = 4
half_size = map_size / 2

boundaries = [
    Entity(model='cube', color=color.rgba(20, 20, 20, 255), scale=(map_size, wall_height, wall_thickness), position=(0, wall_height/2 - 0.5, half_size), collider='box', is_terrain=True),
    Entity(model='cube', color=color.rgba(20, 20, 20, 255), scale=(map_size, wall_height, wall_thickness), position=(0, wall_height/2 - 0.5, -half_size), collider='box', is_terrain=True),
    Entity(model='cube', color=color.rgba(20, 20, 20, 255), scale=(wall_thickness, wall_height, map_size), position=(half_size, wall_height/2 - 0.5, 0), collider='box', is_terrain=True),
    Entity(model='cube', color=color.rgba(20, 20, 20, 255), scale=(wall_thickness, wall_height, map_size), position=(-half_size, wall_height/2 - 0.5, 0), collider='box', is_terrain=True)
]

obstacles = []
obstacles.append(Entity(model='cube', color=color.gray, position=(0, 0.5, 0), scale=(6, 3, 6), collider='box', is_terrain=True))

obstacle_positions = [(-8, 8), (8, -8), (-12, 0), (12, 0), (0, 12), (0, -12)]
for x, z in obstacle_positions:
    obstacles.append(Entity(model='cube', color=color.gray, position=(x, 0.5, z), scale=(3, 2, 3), collider='box', is_terrain=True))

# --- INIT PLAYERS ---
p1_controls = {'up': 'w', 'down': 's', 'left': 'a', 'right': 'd', 'attack': '1', 'skill1': '2', 'skill2': '3'}
p2_controls = {'up': 'up arrow', 'down': 'down arrow', 'left': 'left arrow', 'right': 'right arrow', 'attack': 'j', 'skill1': 'n', 'skill2': 'm'}

p1 = None
p2 = None

def spawn_players():
    global p1, p2
    if p1: destroy(p1)
    if p2: destroy(p2)
    p1 = Player1(start_pos=Vec3(-10, 0.5, -10), controls=p1_controls)
    p2 = Player2(start_pos=Vec3(10, 0.5, 10), controls=p2_controls)
    p1.enemy_target = p2
    p2.enemy_target = p1

spawn_players()

# --- UI HỆ THỐNG ---
ui_parent = Entity(parent=camera.ui)
p1_hp_text = Text(parent=ui_parent, position=(-0.85, 0.45), text="P1 HP: 100", scale=1.5, color=color.cyan)
p2_hp_text = Text(parent=ui_parent, position=(0.65, 0.45), text="P2 HP: 100", scale=1.5, color=color.red)
p1_cd_text = Text(parent=ui_parent, position=(-0.85, 0.40), text="S1: Ready | S2: Ready", scale=1.2, color=color.cyan)
p2_cd_text = Text(parent=ui_parent, position=(0.65, 0.40), text="S1: Ready | S2: Ready", scale=1.2, color=color.red)

game_over_panel = Entity(parent=camera.ui, enabled=False, z=-10)
Entity(parent=game_over_panel, model='quad', color=color.rgba(0,0,0,150), scale=(2, 2), z=1)
winner_text = Text(parent=game_over_panel, text="WINNER", origin=(0, 0), scale=3, y=0.1, z=-1)

def restart_game():
    for e in scene.entities[:]:
        if not (getattr(e, 'is_terrain', False) or getattr(e, 'is_ground', False)):
            if e.parent == scene and e.__class__.__name__ not in ['Camera', 'Ursina', 'Sky', 'DirectionalLight']:
                destroy(e)
    spawn_players()
    game_over_panel.enabled = False
    application.resume()

Button(parent=game_over_panel, text='RESTART', scale=(0.2, 0.1), y=-0.1, color=color.azure, on_click=restart_game, z=-1)

def update():
    if game_over_panel.enabled:
        return

    handle_player_movement(p1)
    handle_player_movement(p2)
    action_queue.process_all_actions()

    if hasattr(p1, 'hp'): p1_hp_text.text = f"P1 HP: {int(p1.hp)}"
    if hasattr(p2, 'hp'): p2_hp_text.text = f"P2 HP: {int(p2.hp)}"
    
    if hasattr(p1, 'cooldown1') and hasattr(p1, 'cooldown2'):
        cd1 = f"{p1.cooldown1:.1f}s" if p1.cooldown1 > 0 else "Ready"
        cd2 = f"{p1.cooldown2:.1f}s" if p1.cooldown2 > 0 else "Ready"
        p1_cd_text.text = f"S1: {cd1} | S2: {cd2}"

    if hasattr(p2, 'cooldown1') and hasattr(p2, 'cooldown2'):
        cd1 = f"{p2.cooldown1:.1f}s" if p2.cooldown1 > 0 else "Ready"
        cd2 = f"{p2.cooldown2:.1f}s" if p2.cooldown2 > 0 else "Ready"
        p2_cd_text.text = f"S1: {cd1} | S2: {cd2}"
        
    if hasattr(p1, 'hp') and p1.hp <= 0:
        winner_text.text = "PLAYER 2 WINS!"
        winner_text.color = color.red
        game_over_panel.enabled = True
        application.pause()
    elif hasattr(p2, 'hp') and p2.hp <= 0:
        winner_text.text = "PLAYER 1 WINS!"
        winner_text.color = color.cyan
        game_over_panel.enabled = True
        application.pause()

    if hasattr(p1, 'move_speed'): p1.move_speed = p1.base_speed
    if hasattr(p2, 'move_speed'): p2.move_speed = p2.base_speed

# --- UI TOOLTIPS ---
tutorial_parent = Entity(parent=ui_parent, enabled=False)
tutorial_bg = Entity(parent=tutorial_parent, model='quad', color=color.black, scale=(1.5, 0.9), position=(0, 0), z=1)
tut_text = Text(parent=tutorial_parent, text=" ", origin=(-0.5, 0.5), position=(-0.7, 0.4), scale=1.0, wordwrap=44, line_height=1.1, color=color.white, z=-1)

def update_tutorial_text():
    desc1 = getattr(p1, 'description', 'P1 Description Missing').replace("<orange>", "").replace("</orange>", "").replace("<violet>", "").replace("</violet>", "")
    desc2 = getattr(p2, 'description', 'P2 Description Missing').replace("<gold>", "").replace("</gold>", "").replace("<lime>", "").replace("</lime>", "")
    controls_info = "--- CONTROLS ---\nP1: WASD | 1 (Đánh) | 2 (S1) | 3 (S2)\nP2: Arrows | J (Đánh) | N (S1) | M (S2)\nPress 'F' for Feedback."
    tut_text.text = f"--- PLAYER 1 ---\n{desc1}\n\n--- PLAYER 2 ---\n{desc2}\n\n{controls_info}"

update_tutorial_text()

# --- UI FEEDBACK ---
feedback_panel = Entity(parent=ui_parent, model='quad', color=color.rgba(30, 30, 80, 240), scale=(0.6, 0.3), position=(0, 0), z=-1)
Text(parent=feedback_panel, text="Submit Bug / Feedback", origin=(0, 2), scale=1.5, z=-1)
feedback_input = InputField(parent=feedback_panel, y=0.05, max_lines=1)

def submit_feedback():
    if feedback_input.text:
        with open('feedback.txt', 'w', encoding='utf-8') as f:
            f.write(feedback_input.text)
        application.quit()

Button(parent=feedback_panel, text='Submit & Exit', scale=(0.4, 0.15), y=-0.2, color=color.azure, on_click=submit_feedback)
feedback_panel.enabled = False

def input(key):
    if key == p1.controls['attack']: handle_player_attack(p1)
    if key == p1.controls['skill1']: handle_player_skill1(p1)
    if key == p1.controls['skill2']: handle_player_skill2(p1)
    if key == p2.controls['attack']: handle_player_attack(p2)
    if key == p2.controls['skill1']: handle_player_skill1(p2)
    if key == p2.controls['skill2']: handle_player_skill2(p2)
    if key == 't': tutorial_parent.enabled = not tutorial_parent.enabled
    if key == 'f': feedback_panel.enabled = not feedback_panel.enabled
    if tutorial_parent.enabled:
        if key == 'scroll up': tut_text.y = max(0.4, tut_text.y - 0.05)
        elif key == 'scroll down': tut_text.y = min(4.0, tut_text.y + 0.05)

app.run()
