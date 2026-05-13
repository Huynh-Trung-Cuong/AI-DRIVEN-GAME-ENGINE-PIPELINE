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
    # Nếu không va chạm thì thôi
    if not check_world_collision(player.position, player.position, player.scale, [player]):
        return

    # Thử đẩy ra theo các hướng chính với khoảng cách tăng dần
    push_dist = 0.2
    directions = [Vec3(1,0,0), Vec3(-1,0,0), Vec3(0,0,1), Vec3(0,0,-1)]

    for i in range(1, 10): # Thử tối đa 10 bước nhảy
        for d in directions:
            test_pos = player.position + d * push_dist * i
            if not check_world_collision(test_pos, test_pos, player.scale, [player]):
                player.position = test_pos
                return

# --- ATTACK SYSTEM (Centralized) ---
class Projectile(Entity):
    def __init__(self, start_pos, direction, owner, **kwargs):
        super().__init__(
            model='cube',
            color=owner.color,
            scale=0.3,
            position=start_pos,
            collider='box',
            **kwargs
        )
        self.direction = direction
        self.owner = owner
        self.speed = 25
        self.damage = 10
        destroy(self, delay=2.0) # Tự hủy sau 2s

    def update(self):
        old_pos = Vec3(self.position)
        new_pos = self.position + self.direction * self.speed * time.dt
        
        # 1. Check va chạm địa hình (Bỏ qua owner và enemy target để xử lý riêng)
        if check_world_collision(old_pos, new_pos, self.scale, [self, self.owner, self.owner.enemy_target]):
            destroy(self)
            return

        # 2. Check va chạm kẻ địch (CCD)
        enemy = self.owner.enemy_target
        from dsa import check_minkowski_ccd
        if check_minkowski_ccd(old_pos, new_pos, self.scale, enemy.position, enemy.position, enemy.scale):
            # Gây sát thương thông qua action_queue toàn cục
            action_queue.push_action(2, enemy.take_damage, self.damage)
            # Hiệu ứng va chạm
            impact = Entity(model='cube', color=self.color, scale=0.5, position=new_pos)
            impact.animate_scale(0, duration=0.1)
            destroy(impact, delay=0.1)
            destroy(self)
            return
            
        self.position = new_pos

def handle_player_attack(player):
    if player.sm.current_state in ["IDLE", "MOVE"]:
        if player.sm.request_transition("ATTACK"):
            # Bắn projectile
            Projectile(start_pos=player.position + Vec3(0, 0.5, 0) + player.direction * 1.2, 
                      direction=player.direction, 
                      owner=player)
            # Quay lại IDLE sau 0.2s
            invoke(setattr, player.sm, 'current_state', 'IDLE', delay=0.2)

# --- MOVEMENT SYSTEM ---
def handle_player_movement(player):
    if player.sm.current_state not in ["IDLE", "MOVE"]:
        return

    # 1. Lấy input thô
    move_dir = Vec3(
        held_keys[player.controls['right']] - held_keys[player.controls['left']],
        0,
        held_keys[player.controls['up']] - held_keys[player.controls['down']]
    )

    if move_dir.length() > 0:
        move_dir = move_dir.normalized()
        player.direction = move_dir # Cập nhật hướng di chuyển gần đây nhất

        # 2. Xoay tức thì cho tất cả Player để tối ưu trải nghiệm (Sử dụng lerp tốc độ cao)
        target_rot = math.degrees(math.atan2(move_dir.x, move_dir.z))
        player.rotation_y = lerp(player.rotation_y, target_rot, time.dt * 50)

        # 3. Di chuyển trực tiếp theo input
        final_move = move_dir * player.base_speed * time.dt

        # 4. Check va chạm và cập nhật vị trí (Sử dụng CCD)
        old_pos = Vec3(player.position)
        new_pos = player.position + final_move
        if not check_world_collision(old_pos, new_pos, player.scale, [player]):
            player.position = new_pos

        player.sm.request_transition("MOVE")
    else:
        player.sm.request_transition("IDLE")

    # 5. Giải kẹt (Anti-stuck mechanism)
    resolve_stuck(player)


# --- MAP & ĐỊA HÌNH ---
map_size = 35
ground = Entity(model='cube', color=color.dark_gray, scale=(map_size, 1, map_size), position=(0, -0.5, 0), collider='box', is_ground=True, is_terrain=True)

# 1. Chặn rìa map (Tạo 4 bức tường xung quanh)
wall_thickness = 2
wall_height = 4
half_size = map_size / 2

boundaries = [
    Entity(model='cube', color=color.rgba(20, 20, 20, 255), scale=(map_size, wall_height, wall_thickness), position=(0, wall_height/2 - 0.5, half_size), collider='box', is_terrain=True),  # Tường Bắc
    Entity(model='cube', color=color.rgba(20, 20, 20, 255), scale=(map_size, wall_height, wall_thickness), position=(0, wall_height/2 - 0.5, -half_size), collider='box', is_terrain=True), # Tường Nam
    Entity(model='cube', color=color.rgba(20, 20, 20, 255), scale=(wall_thickness, wall_height, map_size), position=(half_size, wall_height/2 - 0.5, 0), collider='box', is_terrain=True),  # Tường Đông
    Entity(model='cube', color=color.rgba(20, 20, 20, 255), scale=(wall_thickness, wall_height, map_size), position=(-half_size, wall_height/2 - 0.5, 0), collider='box', is_terrain=True)   # Tường Tây
]

# 2. Sinh chướng ngại vật có bố cục (Đấu trường thực thụ)
obstacles = []
# Khối trung tâm lớn chặn giữa map
obstacles.append(Entity(model='cube', color=color.gray, position=(0, 0.5, 0), scale=(6, 3, 6), collider='box', is_terrain=True))

# Các trụ/khối được đặt đối xứng, chừa không gian ở (-10, -10) và (10, 10) cho Player
obstacle_positions = [
    (-8, 8), (8, -8), (-12, 0), (12, 0), (0, 12), (0, -12)
]
for x, z in obstacle_positions:
    obstacles.append(Entity(model='cube', color=color.gray, position=(x, 0.5, z), scale=(3, 2, 3), collider='box', is_terrain=True))

# --- INIT PLAYERS (PIPELINE MỚI) ---
p1_controls = {'up': 'w', 'down': 's', 'left': 'a', 'right': 'd', 'attack': '1', 'skill1': '2', 'skill2': '3'}
p2_controls = {'up': 'up arrow', 'down': 'down arrow', 'left': 'left arrow', 'right': 'right arrow', 'attack': 'j', 'skill1': 'n', 'skill2': 'm'}

p1 = Player1(start_pos=Vec3(-10, 0.5, -10), controls=p1_controls)
p2 = Player2(start_pos=Vec3(10, 0.5, 10), controls=p2_controls)

p1.enemy_target = p2
p2.enemy_target = p1

# --- UI HỆ THỐNG ---
ui_parent = Entity(parent=camera.ui)

# UI Máu
p1_hp_text = Text(parent=ui_parent, position=(-0.85, 0.45), text="P1 HP: 100", scale=1.5, color=color.cyan)
p2_hp_text = Text(parent=ui_parent, position=(0.65, 0.45), text="P2 HP: 100", scale=1.5, color=color.red)

# UI Cooldown (Hồi chiêu)
p1_cd_text = Text(parent=ui_parent, position=(-0.85, 0.40), text="S1: Ready | S2: Ready", scale=1.2, color=color.cyan)
p2_cd_text = Text(parent=ui_parent, position=(0.65, 0.40), text="S1: Ready | S2: Ready", scale=1.2, color=color.red)

def update():
    # 1. Hệ thống di chuyển (Centralized)
    handle_player_movement(p1)
    handle_player_movement(p2)

    # 2. Xử lý Heap Actions (Cuối frame)
    action_queue.process_all_actions()

    # 3. Cập nhật Máu
    if hasattr(p1, 'hp'): p1_hp_text.text = f"P1 HP: {int(p1.hp)}"
    if hasattr(p2, 'hp'): p2_hp_text.text = f"P2 HP: {int(p2.hp)}"
    
    # Cập nhật UI Cooldown Player 1
    if hasattr(p1, 'cooldown1') and hasattr(p1, 'cooldown2'):
        cd1 = f"{p1.cooldown1:.1f}s" if p1.cooldown1 > 0 else "Ready"
        cd2 = f"{p1.cooldown2:.1f}s" if p1.cooldown2 > 0 else "Ready"
        p1_cd_text.text = f"S1: {cd1} | S2: {cd2}"

    # Cập nhật UI Cooldown Player 2
    if hasattr(p2, 'cooldown1') and hasattr(p2, 'cooldown2'):
        cd1 = f"{p2.cooldown1:.1f}s" if p2.cooldown1 > 0 else "Ready"
        cd2 = f"{p2.cooldown2:.1f}s" if p2.cooldown2 > 0 else "Ready"
        p2_cd_text.text = f"S1: {cd1} | S2: {cd2}"
        
    # Logic Thắng/Thua
    if hasattr(p1, 'hp') and p1.hp <= 0:
        Text(parent=ui_parent, text="PLAYER 2 WINS!", position=(0, 0), origin=(0,0), scale=3, color=color.red)
        application.pause()
    elif hasattr(p2, 'hp') and p2.hp <= 0:
        Text(parent=ui_parent, text="PLAYER 1 WINS!", position=(0, 0), origin=(0,0), scale=3, color=color.cyan)
        application.pause()

# --- 3. UI TOOLTIPS (T) - BẢN FIX TRÀN CHỮ ---
tutorial_parent = Entity(parent=ui_parent, enabled=False)

# Mở rộng chiều ngang của Background (scale X từ 1.4 lên 1.5) để bao trọn text
tutorial_bg = Entity(parent=tutorial_parent, model='quad', color=color.black, scale=(1.5, 0.9), position=(0, 0), z=1)

# CRITICAL: 
# - wordwrap=44: Giảm xuống 44 để đảm bảo text luôn nằm gọn trong background 1.5
# - scale=1.0: Giảm nhẹ scale để text thanh thoát hơn và tránh tràn.
# - line_height=1.1: Giảm nhẹ giãn dòng để chứa được nhiều nội dung hơn theo chiều dọc.
tut_text = Text(parent=tutorial_parent, text=" ", origin=(-0.5, 0.5), position=(-0.7, 0.4), scale=1.0, wordwrap=44, line_height=1.1, color=color.white, z=-1)

def update_tutorial_text():
    desc1 = getattr(p1, 'description', 'P1 Description Missing')
    desc2 = getattr(p2, 'description', 'P2 Description Missing')
    
    # Loại bỏ các tag màu cũ để đồng bộ trắng đen
    desc1 = desc1.replace("<orange>", "").replace("</orange>", "").replace("<violet>", "").replace("</violet>", "")
    desc2 = desc2.replace("<gold>", "").replace("</gold>", "").replace("<lime>", "").replace("</lime>", "")
    
    controls_info = (
        "--- CONTROLS ---\n"
        "P1: WASD (Di chuyển) | 1 (Đánh) | 2 (Skill 1) | 3 (Skill 2)\n"
        "P2: Arrows (Di chuyển) | J (Đánh) | N (Skill 1) | M (Skill 2)\n"
        "Press 'F' for Feedback."
    )
    
    # Ghép nối chuỗi hoàn chỉnh
    tut_text.text = f"--- PLAYER 1 ---\n{desc1}\n\n--- PLAYER 2 ---\n{desc2}\n\n{controls_info}"

update_tutorial_text()

# --- UI FEEDBACK (F) ---
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
    # --- CENTRALIZED ATTACK INPUT ---
    if key == p1.controls['attack']: handle_player_attack(p1)
    if key == p2.controls['attack']: handle_player_attack(p2)

    # Bật / tắt UI
    if key == 't':
        tutorial_parent.enabled = not tutorial_parent.enabled
    if key == 'f':
        feedback_panel.enabled = not feedback_panel.enabled

    # Logic cuộn chuột (Scroll) cho bảng thông tin
    if tutorial_parent.enabled:
        if key == 'scroll up':
            # Giới hạn không cho cuộn ngược lên quá vị trí ban đầu (0.4 là mốc position Y ở trên)
            tut_text.y = max(0.4, tut_text.y - 0.05) 
        elif key == 'scroll down':
            # Lướt xuống dưới (đẩy tọa độ Y của text lên cao)
            # Tăng giới hạn cuộn tối đa lên 4.0 để hỗ trợ mô tả cực dài
            tut_text.y = min(4.0, tut_text.y + 0.05) 

app.run()