#!/usr/bin/env python3
"""Parse SWMF .outs AMR block-structured file and write Tecplot ASCII."""
import struct, numpy as np, sys, os

class FortranFile:
    def __init__(self, data):
        self.data = data; self.pos = 0
        self.n_records = 0
    def next_record(self):
        if self.pos + 4 > len(self.data): return None, None
        rlen = struct.unpack_from('<I', self.data, self.pos)[0]
        if rlen == 0 or self.pos + 8 + rlen > len(self.data): return None, None
        close = struct.unpack_from('<I', self.data, self.pos + 4 + rlen)[0]
        if close != rlen: return None, None
        body = self.data[self.pos+4:self.pos+4+rlen]
        self.pos += 4 + rlen + 4
        self.n_records += 1
        return rlen, body

def parse_outs(path):
    with open(path, 'rb') as f:
        raw = f.read()
    
    ff = FortranFile(raw)
    blocks = []
    var_names = None
    block_coords = []
    block_fields = []
    
    while True:
        r, body = ff.next_record()
        if r is None: break
        
        # Check if ASCII header line
        if r > 100 and all(32 <= b < 127 or b == 10 for b in body):
            text = body.decode('ascii').strip()
            # Variable names header
            if 'x y' in text and ('Rho' in text or 'Bx' in text):
                var_names = text.split()
                print(f"  Found var names: {var_names[:8]}...")
            continue
        
        # Check if data record
        f32 = np.frombuffer(body, dtype=np.float32)
        if len(f32) == 8192:
            # Coordinate record (for a 64x64 or 128x32 grid)
            nx = 64; ny = 128  # typical BATSRUS block
            if abs(len(f32) - nx*ny) > 10:
                nx = int(np.sqrt(len(f32))); ny = len(f32)//nx
            block_coords.append((r, f32, nx, ny))
        elif len(f32) == 4096 and var_names and len(block_coords) > 0:
            # Field data record
            block_fields.append(f32)
        else:
            # Other (block header params, etc.)
            pass
    
    print(f"  Coordinate records: {len(block_coords)}")
    print(f"  Field records: {len(block_fields)}")
    
    # Build combined X, Y grids and field arrays
    if not var_names or not block_coords:
        print("  ERROR: could not determine variable names or blocks")
        return
    
    n_vars = len(var_names)
    n_fields_per_block = len(block_fields) // len(block_coords) if block_coords else 0
    print(f"  Fields per block: {n_fields_per_block}")
    print(f"  Total variables: {n_vars}")
    
    # Print some diagnostics
    for i in range(min(3, len(block_coords))):
        r, f32, nx, ny = block_coords[i]
        print(f"  Block {i}: coord record len={r}, grid={nx}x{ny}, f32 range=[{f32.min():.1f},{f32.max():.1f}]")
    
    for i in range(min(3, n_fields_per_block)):
        vals = block_fields[i]
        print(f"  Field {i}: len={len(vals)}, range=[{np.nanmin(vals):.4g},{np.nanmax(vals):.4g}]")


path = sys.argv[1] if len(sys.argv) > 1 else r'Z:\SWMF\run_test\RESULTS\GM\z=0_ful_3_n00000000_00000911.outs'
print(f"Parsing: {path}")
parse_outs(path)
