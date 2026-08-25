#!/usr/bin/env python3
"""Generate a steady IMF.dat solar-wind driver for one scan condition.
Usage: python3 make_imf.py <out_path> --bz -5.0 --by 0.0 --bx 3.2 --vx -400 --rho 12.0 --temp 3.0e6
Writes 10 records (00:01..00:07) with constant values; SWMF extrapolates beyond.
"""
import sys, argparse

HEADER = "year mo dy hr min sec msec bx by bz vx vy vz dens temp"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out_path')
    ap.add_argument('--bz', type=float, default=-4.8)
    ap.add_argument('--by', type=float, default=-1.1)
    ap.add_argument('--bx', type=float, default=3.2)
    ap.add_argument('--vx', type=float, default=-1284.0)
    ap.add_argument('--rho', type=float, default=12.16)
    ap.add_argument('--temp', type=float, default=3346615.2)
    args = ap.parse_args()
    lines = ["#START", HEADER]
    t = 1.0
    for i in range(10):
        lines.append(" 2014  4 10  0 %02d 00 000   %7.2f  %7.2f  %7.2f %8.2f  %7.2f   %6.2f   %8.2f   %10.1f"
                     % (min(t, 7), args.bx, args.by, args.bz, args.vx, -29.12, 42.35, args.rho, args.temp))
        t += 0.66
    with open(args.out_path, 'w') as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", args.out_path)

if __name__ == '__main__':
    main()
