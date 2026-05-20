from ursina import *
from dsa import check_minkowski_ccd

class BasicProjectile(Entity):
    def __init__(self, start_pos, direction, owner, damage=10, speed=25, **kwargs):
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
        self.speed = speed
        self.damage = damage
        destroy(self, delay=2.0)

    def update(self):
        from player import action_queue, check_world_collision
        
        old_pos = Vec3(self.position)
        new_pos = self.position + self.direction * self.speed * time.dt
        
        # 1. Check va chạm địa hình
        if check_world_collision(old_pos, new_pos, self.scale, [self, self.owner]):
            destroy(self)
            return

        # 2. Check va chạm kẻ địch
        enemy = self.owner.enemy_target
        if enemy and check_minkowski_ccd(old_pos, new_pos, self.scale, enemy.position, enemy.position, enemy.scale):
            action_queue.push_action(2, enemy.take_damage, self.damage, self)
            
            # VFX đơn giản
            impact = Entity(model='cube', color=self.color, scale=0.5, position=new_pos)
            impact.animate_scale(0, duration=0.1)
            destroy(impact, delay=0.1)
            
            destroy(self)
            return
            
        self.position = new_pos
