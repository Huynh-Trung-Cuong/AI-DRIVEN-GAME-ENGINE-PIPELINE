**CHARACTER 1: DUNE JAILER**

**[Playstyle]**
Dune Jailer is a mid-range catcher who wins by forcing short, ugly trades. The kit is simple: land a chain, drag the target into your preferred spacing, then threaten a fixed sand burst that becomes much harsher if the enemy is already pinned by your chains.

**[Character 1 Skill Kit]**
**Skill 1.1: Dusthook Lash**
*   **Core Idea:** Fire a chained hook straight ahead. On hit, it damages, drags the enemy slightly toward you, and applies `Shackled` to set up the second skill.
*   **Technical Stats:** [Cooldown: 4.0s]
*   **VFX:** A heavy iron chain wrapped in blowing sand; on hit, sand snaps inward around the target's feet.
```plaintext
Phase 1 - Cast (0.12s startup):
- Lock facing direction.
- Create 1 chain projectile from the caster's center.

Phase 2 - Projectile and hit:
- Projectile range: 4.0 units.
- Projectile speed: 12 units per second.
- Projectile width: 0.28 units.
- The projectile stops on the first enemy hit or at max range, then is deleted.
- On enemy hit: deal 8 damage, pull the enemy 0.9 units toward the caster, and apply Shackled for 2.2s.
- Shackled: the target's move speed is reduced by 20%.
- If the enemy would be pulled through a wall, stop the pull at the wall edge.
- On miss: the projectile is deleted at max range with no further effect.
```

**Skill 1.2: Pitbreaker Crush**
*   **Core Idea:** After a short windup, the jailer detonates a sand pit at a fixed point in front. It is a basic space-check by itself, but it becomes a brutal confirm if it hits a `Shackled` target.
*   **Technical Stats:** [Cooldown: 6.5s]
*   **VFX:** A dark sand circle swells from the ground, then erupts upward with chain fragments and a blunt shockwave.
```plaintext
Phase 1 - Windup (0.32s startup):
- Lock facing direction.
- Mark a target point 1.6 units straight ahead of the caster.
- Spawn 1 sand zone at that point with a visible radius indicator.

Phase 2 - Burst:
- After the startup ends, the zone bursts once and is immediately deleted.
- Zone radius: 0.95 units.
- Base effect on enemies inside the zone on the burst frame: 12 damage and push 0.6 units away from the zone center.
- Combo link with Skill 1.1:
  If an enemy inside the zone is currently Shackled, consume Shackled and replace the base effect with 18 damage plus 0.55s stun.
- If the enemy is not Shackled, the skill never stuns and always uses the base effect.
- The zone does not persist after the burst frame.
```

---

**CHARACTER 2: HARECLEAVER**

**[Playstyle]**
Harecleaver is a quick entry-and-exit duelist that plays around one sharp opening. The character hops into close range, clips the target with a fast axe cut, then cashes that tempo into a heavier chop before the opponent resets spacing.

**[Character 2 Skill Kit]**
**Skill 2.1: Springheel Cut**
*   **Core Idea:** Leap a short distance in the facing direction and swing on landing. The landing hit is the main opener and applies `Off-Balance` for the follow-up chop.
*   **Technical Stats:** [Cooldown: 3.8s]
*   **VFX:** A low sand-dusting hop with a bright crescent axe trail at landing.
```plaintext
Phase 1 - Hop (0.18s movement):
- Lock facing direction at cast start.
- Move 2.0 units straight forward.
- The caster can pass through straight projectiles during this movement; those projectiles are deleted on contact.
- The caster does not ignore walls or enemy bodies.

Phase 2 - Landing slash:
- At the end of the hop, create a 1.1-unit-radius half-circle hitbox in front of the caster for 0.08s.
- First enemy hit takes 9 damage and is pushed 0.4 units away from the caster.
- The hit also applies Off-Balance for 2.0s.
- Off-Balance: the target's turn rate is reduced by 35%.
- If no enemy is hit, Off-Balance is not applied and the skill simply ends.
```

**Skill 2.2: Cleaver Drop**
*   **Core Idea:** A committed overhead axe strike at a fixed point in front of the rabbit. It is serviceable raw, but much faster and deadlier after `Springheel Cut` has already opened the target.
*   **Technical Stats:** [Cooldown: 6.2s]
*   **VFX:** The axe is raised high with a brief white flash, then slams down in a straight dirt-splitting line.
```plaintext
Phase 1 - Startup:
- Default startup: 0.30s.
- If at least one enemy currently has Off-Balance when this skill is cast, startup becomes 0.18s instead.
- Lock facing direction.

Phase 2 - Axe line:
- Create 1 rectangular hitbox 1.9 units long and 0.85 units wide directly in front of the caster for 0.10s.
- Base effect on first enemy hit: 13 damage and 0.45-unit push directly away from the caster.
- Combo link with Skill 2.1:
  If the hit enemy is currently Off-Balance, consume Off-Balance and replace the base effect with 18 damage and 0.45s stun.
- If the enemy is not Off-Balance, the skill never stuns and always uses the base effect.
- The hitbox is deleted after the active window.
```

---

# **MATCHUP & BALANCE ANALYSIS**
1. **Win Conditions:** `Dune Jailer` wins by landing `Dusthook Lash` at mid range, dragging `Harecleaver` into uncomfortable spacing, and forcing respect on `Pitbreaker Crush` at the fixed 1.6-unit threat point. `Harecleaver` wins by using `Springheel Cut` to break through straight-line control, tagging `Off-Balance`, and quickly converting that entry into `Cleaver Drop` before the sand player can re-center.
2. **Counterplay & Balance:** `Dusthook Lash` is threatening, but it is still a straight projectile and can be bypassed by the hop phase of `Springheel Cut` if timed well. `Pitbreaker Crush` hits hard only after a confirmed chain and has real startup, so the rabbit can beat it by hopping past the marked zone or by forcing it raw. `Cleaver Drop` becomes much scarier after `Off-Balance`, but it is still a fixed frontal line; if the rabbit guesses wrong, the recovery window leaves room for chain punishment.
3. **Special Skill Interactions:** `Dusthook Lash` projectile and `Springheel Cut` hop resolve by priority: if the rabbit's hop body touches the chain projectile during the hop phase, delete the projectile and do not apply damage or `Shackled`. If `Pitbreaker Crush` burst frame and `Springheel Cut` landing slash hit on the same frame, apply both damages; then resolve forced movement from the burst push before the slash push. If `Dusthook Lash` hits a target during `Cleaver Drop` startup, the pull is applied immediately and does not cancel the axe skill; the axe still fires in its locked original direction unless the stun version later lands. If `Cleaver Drop` and `Pitbreaker Crush` hit each other on the same frame, apply both damages, then apply stuns, and if both stuns apply at once both characters are stunned normally. Resolve same-frame events in this order: projectile deletion, state application (`Shackled`, `Off-Balance`), damage, pull effects, push effects, then stun timers.
