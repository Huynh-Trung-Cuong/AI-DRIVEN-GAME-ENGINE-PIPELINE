import re

with open('player.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace SimpleProjectile usage and fix execute_attack
old_exec = """    def execute_attack(self):
        if not self.can_act():
            return False
        if not self.change_state("ATTACK"):
            return False
        self.attack_fired = False
        return True

    def _fire_attack(self):
        spawn = self.position + Vec3(0, 0.25, 0) + self.locked_direction * 0.65
        SimpleProjectile(spawn, self.locked_direction, self, damage=6, speed=15.0, max_range=6.0)"""

new_exec = """    def execute_attack(self):
        if not self.can_act():
            return False
        if getattr(self, "active_attack", None) and not getattr(self.active_attack, "destroyed", False) and not getattr(self.active_attack, "dead", False):
            return False
        if not self.change_state("ATTACK"):
            return False
        self.locked_direction = _safe_dir(self.direction)
        self.attack_fired = False
        return True

    def _fire_attack(self):
        from combat import BasicProjectile
        spawn = self.position + Vec3(0, 0.25, 0) + self.locked_direction * 0.65
        self.active_attack = BasicProjectile(spawn, self.locked_direction, self, damage=6, speed=15.0)"""

content = content.replace(old_exec, new_exec)

# Add PlayerStatusHUD before BasePlayer
hud_code = """class PlayerStatusHUD(Entity):
    def __init__(self, owner, position, align_left=True):
        super().__init__(parent=camera.ui)
        self.owner = owner
        origin_x = -0.5 if align_left else 0.5
        self.text = Text(parent=self, position=position, origin=(origin_x, 0.5), scale=0.9, color=owner.color)

    def update(self):
        p = self.owner
        if getattr(p, "destroyed", False) or getattr(p, "dead", False):
            return
        cd1 = f"{p.cooldown1:.1f}" if p.cooldown1 > 0 else "ready"
        cd2 = f"{p.cooldown2:.1f}" if p.cooldown2 > 0 else "ready"
        statuses = [name for name, timer in p.statuses.items() if timer > 0]
        buffs = ",".join(statuses[:4]) if statuses else "-"
        
        self.text.text = f"{p.display_name}\\nHP {int(p.hp)}/100 | S1 {cd1} | S2 {cd2}\\n{buffs}"
        self.text.color = p.original_color


class BasePlayer(Entity):"""

content = content.replace('class BasePlayer(Entity):', hud_code)

# Add hud_position to constructors
old_init_base = """    def __init__(self, start_pos, controls, color_skin, **kwargs):
        super().__init__(model="cube", collider="box", color=color_skin, position=start_pos, scale=(1, 1, 1), **kwargs)
        self.original_color = color_skin"""

new_init_base = """    def __init__(self, start_pos, controls, color_skin, hud_position=(-0.85, 0.34), hud_align_left=True, **kwargs):
        super().__init__(model="cube", collider="box", color=color_skin, position=start_pos, scale=(1, 1, 1), **kwargs)
        self.original_color = color_skin
        self.hud = PlayerStatusHUD(self, hud_position, hud_align_left)"""

content = content.replace(old_init_base, new_init_base)

old_init_p1 = """    def __init__(self, start_pos, controls, **kwargs):
        super().__init__(start_pos, controls, color.rgb(210, 170, 110), **kwargs)"""

new_init_p1 = """    def __init__(self, start_pos, controls, hud_position=(-0.85, 0.34), hud_align_left=True, **kwargs):
        super().__init__(start_pos, controls, color.rgb(210, 170, 110), hud_position=hud_position, hud_align_left=hud_align_left, **kwargs)"""

content = content.replace(old_init_p1, new_init_p1)

old_init_p2 = """    def __init__(self, start_pos, controls, **kwargs):
        super().__init__(start_pos, controls, color.rgb(190, 225, 145), **kwargs)"""

new_init_p2 = """    def __init__(self, start_pos, controls, hud_position=(0.85, 0.34), hud_align_left=False, **kwargs):
        super().__init__(start_pos, controls, color.rgb(190, 225, 145), hud_position=hud_position, hud_align_left=hud_align_left, **kwargs)"""

content = content.replace(old_init_p2, new_init_p2)


# Add held_keys to Player1 and Player2 update
old_update_p1 = """    def update(self):
        if not self.common_update():
            return

        if self.sm.current_state == "ATTACK":"""

new_update_p1 = """    def update(self):
        if not self.common_update():
            return

        if held_keys[self.controls["attack"]] and self.sm.current_state in ("IDLE", "MOVE"):
            self.execute_attack()

        if self.sm.current_state == "ATTACK":"""

content = content.replace(old_update_p1, new_update_p1)

old_update_p2 = """    def update(self):
        if not self.common_update():
            return

        if self.sm.current_state == "ATTACK":"""

new_update_p2 = """    def update(self):
        if not self.common_update():
            return

        if held_keys[self.controls["attack"]] and self.sm.current_state in ("IDLE", "MOVE"):
            self.execute_attack()

        if self.sm.current_state == "ATTACK":"""

content = content.replace(old_update_p2, new_update_p2)


with open('player.py', 'w', encoding='utf-8') as f:
    f.write(content)
