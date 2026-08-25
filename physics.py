import numpy as np
from scipy.integrate import solve_ivp

class MagneticField:
    def __init__(self, dipole_moment=1.0):
        # GSE Coordinate System (Geocentric Solar Ecliptic)
        # X: Sun, Z: Ecliptic North, Y: Dusk
        self.tilt_rot = np.radians(23.44) # Earth axial tilt
        self.tilt_mag = np.radians(11.0)  # Magnetic tilt relative to rot axis
        
        # Total tilt in GSE X-Z plane (assuming Summer Solstice for max effect)
        self.total_tilt = self.tilt_rot + self.tilt_mag
        
        # Magnetic moment vector (points South)
        self.m = np.array([-np.sin(self.total_tilt), 0.0, -np.cos(self.total_tilt)]) * dipole_moment
        self.solar_wind_compression = 1.0 # Affected by Kp index
        self.max_range = 10.0 # Default max computation range

    def get_field(self, r_vec):
        r = np.linalg.norm(r_vec)
        if r < 0.1: # Prevent singularity
            return np.zeros(3)
        
        # 1. Earth's dipole field
        r_hat = r_vec / r
        B_earth = (3 * np.dot(self.m, r_hat) * r_hat - self.m) / (r**3)
        
        # 2. Solar wind compression (Dayside +X)
        # Use an image dipole on the dayside to compress field lines
        R_mp = 10.0 / (self.solar_wind_compression ** (1/3)) 
        D = 2.0 * R_mp
        r_image = np.array([D, 0.0, 0.0])
        r_img_vec = r_vec - r_image
        r_img = np.linalg.norm(r_img_vec)
        
        B_image = np.zeros(3)
        if r_img > 0.1:
            r_img_hat = r_img_vec / r_img
            # m_image has reversed x component to cancel normal B at boundary
            m_image = np.array([-self.m[0], self.m[1], self.m[2]]) * (self.solar_wind_compression ** (1/3))
            B_image = (3 * np.dot(m_image, r_img_hat) * r_img_hat - m_image) / (r_img**3)
            
        # 3. Magnetotail stretching (Nightside -X)
        B_tail = np.zeros(3)
        if r_vec[0] < 0:
            z = r_vec[2]
            # Current sheet in equatorial plane stretches lines in X direction
            tail_str = 0.02 * self.solar_wind_compression * np.exp(-abs(z)/2.0)
            B_tail = np.array([-np.sign(z) * tail_str, 0.0, 0.0])

        return B_earth + B_image + B_tail

    def compute_field_lines(self):
        lines = []
        L_shells = [1.5, 2.5, 4.0, 6.0, 8.0]
        
        # Magnetic equatorial axes
        z_m = np.array([np.sin(self.total_tilt), 0.0, np.cos(self.total_tilt)])
        y_m = np.array([0.0, 1.0, 0.0])
        x_m = np.cross(y_m, z_m)
        
        def field_deriv_fwd(t, y):
            B = self.get_field(y)
            B_mag = np.linalg.norm(B)
            if B_mag < 1e-9: return np.zeros(3)
            return B / B_mag

        def field_deriv_bwd(t, y):
            B = self.get_field(y)
            B_mag = np.linalg.norm(B)
            if B_mag < 1e-9: return np.zeros(3)
            return -B / B_mag

        def hit_earth(t, y):
            return np.linalg.norm(y) - 1.0
        hit_earth.terminal = True
        
        def out_of_bounds(t, y):
            return self.max_range - np.linalg.norm(y)
        out_of_bounds.terminal = True

        events = [hit_earth, out_of_bounds]
        max_s = self.max_range * 4.0
        
        for L in L_shells:
            for angle in np.linspace(0, 2*np.pi, 8, endpoint=False):
                start_pos = L * (np.cos(angle)*x_m + np.sin(angle)*y_m)
                
                if np.linalg.norm(start_pos) > self.max_range:
                    continue
                
                # Trace using solve_ivp for rigorous accuracy
                sol_fwd = solve_ivp(field_deriv_fwd, [0, max_s], start_pos, method='RK23', events=events, max_step=0.2)
                sol_bwd = solve_ivp(field_deriv_bwd, [0, max_s], start_pos, method='RK23', events=events, max_step=0.2)
                        
                full_line = [p for p in sol_bwd.y.T[::-1]] + [p for p in sol_fwd.y.T[1:]]
                if len(full_line) > 1:
                    lines.append([p.tolist() for p in full_line])
        return lines

class Particle:
    def __init__(self, q, mass, pos, vel):
        self.q = q
        self.mass = mass
        self.pos = np.array(pos, dtype=float)
        self.vel = np.array(vel, dtype=float)

class SimulationEngine:
    def __init__(self):
        self.b_field = MagneticField(dipole_moment=1.0)
        self.particles = []
        for _ in range(100):
            self.particles.append(self.spawn_particle())
        self.dt = 0.01
        self.needs_field_update = True

    def spawn_particle(self, p=None):
        max_r = self.b_field.max_range
        # Spawn exactly at max_range boundary on the dayside (+X dominant)
        # We sample points on a spherical cap facing the sun
        theta = np.random.uniform(0, 2*np.pi)
        phi = np.random.uniform(0, np.pi/3) # up to 60 degrees from Sun-Earth line
        
        x = max_r * np.cos(phi)
        y = max_r * np.sin(phi) * np.cos(theta)
        z = max_r * np.sin(phi) * np.sin(theta)
        
        pos = np.array([x, y, z])
        
        # Velocity pointing roughly towards Earth (-X) mimicking solar wind
        v_sw = 3.0 * self.b_field.solar_wind_compression
        v_x = -v_sw + np.random.normal(0, 0.5)
        v_y = np.random.normal(0, 0.5)
        v_z = np.random.normal(0, 0.5)
        vel = np.array([v_x, v_y, v_z])
        
        if p is None:
            q = 1.0 if np.random.rand() > 0.5 else -1.0
            return Particle(q=q, mass=0.1, pos=pos, vel=vel)
        else:
            p.pos = pos
            p.vel = vel
            return p

    def set_particle_count(self, count):
        current = len(self.particles)
        if count > current:
            for _ in range(count - current):
                self.particles.append(self.spawn_particle())
        elif count < current:
            self.particles = self.particles[:count]

    def set_solar_activity(self, kp_index):
        # Kp index ranges 0 to 9. We scale compression factor 1.0 to 2.0 based on Kp
        new_comp = 1.0 + (kp_index / 9.0)
        if abs(new_comp - self.b_field.solar_wind_compression) > 0.01:
            self.b_field.solar_wind_compression = new_comp
            self.needs_field_update = True

    def boris_step(self, particle):
        # High precision symplectic Boris Pusher
        q_prime = particle.q / particle.mass
        dt2 = self.dt / 2.0
        
        B = self.b_field.get_field(particle.pos)
        
        t = q_prime * B * dt2
        t_mag2 = np.dot(t, t)
        s = 2.0 * t / (1.0 + t_mag2)
        
        v_minus = particle.vel
        v_prime = v_minus + np.cross(v_minus, t)
        v_plus = v_minus + np.cross(v_prime, s)
        
        particle.vel = v_plus
        particle.pos += particle.vel * self.dt
        
        # Stop particle if it hits Earth (R < 1.0) or exceeds max range
        r_norm = np.linalg.norm(particle.pos)
        if r_norm < 1.0 or r_norm > self.b_field.max_range + 2.0:
            self.spawn_particle(particle)

    def step(self):
        for p in self.particles:
            self.boris_step(p)

    def get_state(self):
        state = []
        for i, p in enumerate(self.particles):
            state.append({
                "id": i,
                "q": p.q,
                "pos": p.pos.tolist(),
                "vel": p.vel.tolist()
            })
        return state
