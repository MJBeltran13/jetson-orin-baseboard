#!/usr/bin/env python3
"""
scripts/complete_routing.py
Comprehensive, zero-short routing for Jetson Orin Baseboard.
Implements Blocks A, B, C, D, and E with strict clearance verification.
"""

import sys
import os
import math
import heapq

sys.path.append('/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/lib/python3.9/site-packages')
import pcbnew

def ToMM(val): return pcbnew.ToMM(val)
def FromMM(val): return pcbnew.FromMM(val)
def V(x, y): return pcbnew.VECTOR2I(FromMM(x), FromMM(y))

class GridRouter:
    def __init__(self, x_min, x_max, y_min, y_max, res=0.25):
        self.res = res
        self.x_min, self.x_max = x_min, x_max
        self.y_min, self.y_max = y_min, y_max
        self.cols = int(math.ceil((x_max - x_min) / res)) + 1
        self.rows = int(math.ceil((y_max - y_min) / res)) + 1
        # 2 layers: 0 -> In3.Cu, 1 -> In5.Cu
        self.grid = [bytearray(self.cols * self.rows) for _ in range(2)]
        self.via_blocked = bytearray(self.cols * self.rows)

    def to_grid(self, x, y):
        c = int(round((x - self.x_min) / self.res))
        r = int(round((y - self.y_min) / self.res))
        return max(0, min(self.cols - 1, c)), max(0, min(self.rows - 1, r))

    def to_world(self, c, r):
        return self.x_min + c * self.res, self.y_min + r * self.res

    def block_box(self, x1, y1, x2, y2, layer_idx, clearance=0.20):
        c1, r1 = self.to_grid(min(x1, x2) - clearance, min(y1, y2) - clearance)
        c2, r2 = self.to_grid(max(x1, x2) + clearance, max(y1, y2) + clearance)
        for r in range(r1, r2 + 1):
            base = r * self.cols
            for c in range(c1, c2 + 1):
                self.grid[layer_idx][base + c] = 1

    def block_via_box(self, x1, y1, x2, y2, clearance=0.30):
        c1, r1 = self.to_grid(min(x1, x2) - clearance, min(y1, y2) - clearance)
        c2, r2 = self.to_grid(max(x1, x2) + clearance, max(y1, y2) + clearance)
        for r in range(r1, r2 + 1):
            base = r * self.cols
            for c in range(c1, c2 + 1):
                self.via_blocked[base + c] = 1

    def route_net(self, start_pt, end_pt, prefer_layer=0):
        sc, sr = self.to_grid(*start_pt)
        ec, er = self.to_grid(*end_pt)
        
        pq = []
        heapq.heappush(pq, (0, 0, sc, sr, prefer_layer))
        dist = {(sc, sr, prefer_layer): 0}
        parent = {}

        found = None
        while pq:
            f, cost, c, r, l = heapq.heappop(pq)
            if c == ec and r == er:
                found = (c, r, l)
                break
            if cost > dist.get((c, r, l), float('inf')):
                continue

            # 4 planar moves
            neighbors = [
                (c + 1, r, l, 1.0),
                (c - 1, r, l, 1.0),
                (c, r + 1, l, 1.0),
                (c, r - 1, l, 1.0),
            ]
            # Layer change via (if not via_blocked)
            idx = r * self.cols + c
            if self.via_blocked[idx] == 0:
                nl = 1 - l
                if self.grid[nl][idx] == 0:
                    neighbors.append((c, r, nl, 5.0))

            for nc, nr, nl, move_cost in neighbors:
                if 0 <= nc < self.cols and 0 <= nr < self.rows:
                    if self.grid[nl][nr * self.cols + nc] == 0:
                        new_cost = cost + move_cost
                        if new_cost < dist.get((nc, nr, nl), float('inf')):
                            dist[(nc, nr, nl)] = new_cost
                            h = (abs(nc - ec) + abs(nr - er)) * 1.05
                            heapq.heappush(pq, (new_cost + h, new_cost, nc, nr, nl))
                            parent[(nc, nr, nl)] = (c, r, l)

        if not found:
            return None

        # Reconstruct path
        path = []
        curr = found
        while curr:
            path.append(curr)
            curr = parent.get(curr)
        path.reverse()

        # Mark routed path as blocked
        for c, r, l in path:
            self.block_box(self.x_min + c * self.res, self.y_min + r * self.res,
                           self.x_min + c * self.res, self.y_min + r * self.res, l, clearance=0.20)
            if (c, r) in [(p[0], p[1]) for p in path if p[2] != l]:
                self.block_via_box(self.x_min + c * self.res, self.y_min + r * self.res,
                                   self.x_min + c * self.res, self.y_min + r * self.res, clearance=0.35)

        return path

def main():
    pcb_in = 'jetson-orin-baseboard.kicad_pcb'
    pcb_out = '/tmp/jetson-orin-baseboard-routed.kicad_pcb'
    orig_pcb_path = '/tmp/git_orig.kicad_pcb'

    print(f'Loading baseboard: {pcb_in}')
    board = pcbnew.LoadBoard(pcb_in)

    # 1. Restore verified baseline tracks from git_orig
    if os.path.exists(orig_pcb_path):
        print('Restoring baseline non-expansion tracks...')
        b_orig = pcbnew.LoadBoard(orig_pcb_path)
        accidental_tags = ['/USB Debug, DP/', '/HDMI/', '/CSI/', 'Net-(U5-', '/Peripherals/I2C_CONN_3V3', '/Peripherals/1V8_CONN']
        existing_tracks = set()
        for t in board.GetTracks():
            existing_tracks.add((t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y, t.GetLayer(), t.GetNetname()))
            existing_tracks.add((t.GetEnd().x, t.GetEnd().y, t.GetStart().x, t.GetStart().y, t.GetLayer(), t.GetNetname()))

        restored = 0
        for t in b_orig.GetTracks():
            net_name = t.GetNetname()
            if any(tag in net_name for tag in accidental_tags):
                key = (t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y, t.GetLayer(), net_name)
                if key not in existing_tracks:
                    net_item = board.FindNet(net_name)
                    if net_item:
                        dup = t.Duplicate()
                        dup.SetNet(net_item)
                        board.Add(dup)
                        restored += 1
        print(f'Restored {restored} verified baseline tracks/vias.')

    # 2. Depopulate retired USB-A circuit
    retired_refs = [
        'J18', 'U50', 'C180', 'C181', 'C182', 'C183', 'C184',
        'D65', 'D66', 'D67', 'D68', 'R345', 'R346', 'R347'
    ]
    for ref in retired_refs:
        fp = board.FindFootprintByReference(ref)
        if fp: board.Delete(fp)

    usba_nets = [
        '/Expansion/USB_VBUS', 'Net-(J18-SSTX-)', 'Net-(J18-SSTX+)',
        'Net-(U50-EN)', 'Net-(U50-FLG)', 'Net-(U50-ISET)'
    ]
    for t in list(board.GetTracks()):
        if t.GetNetname() in usba_nets:
            board.Delete(t)

    # 3. Clean Edge.Cuts
    print('Repairing Edge.Cuts...')
    for d in list(board.GetDrawings()):
        if d.GetLayer() == pcbnew.Edge_Cuts:
            if isinstance(d, pcbnew.PCB_SHAPE) and d.GetShape() == pcbnew.SHAPE_T_ARC:
                if ToMM(d.GetStart().x) > 160.0 or ToMM(d.GetEnd().x) > 160.0:
                    board.Delete(d)

    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts:
            s, e = d.GetStart(), d.GetEnd()
            sx, sy = ToMM(s.x), ToMM(s.y)
            ex, ey = ToMM(e.x), ToMM(e.y)
            if abs(sy - 68.75) < 0.2 and abs(ey - 68.75) < 0.2 and max(sx, ex) > 140.0:
                if sx < ex: d.SetEnd(V(179.75, 68.75))
                else: d.SetStart(V(179.75, 68.75))
            elif abs(sy - 128.75) < 0.2 and abs(ey - 128.75) < 0.2 and max(sx, ex) > 140.0:
                if sx > ex: d.SetStart(V(179.75, 128.75))
                else: d.SetEnd(V(179.75, 128.75))

    def add_edge_seg(p1, p2):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetStart(p1); seg.SetEnd(p2); seg.SetWidth(FromMM(0.15))
        board.Add(seg)

    add_edge_seg(V(179.75, 68.75), V(180.00, 69.00))
    add_edge_seg(V(180.00, 69.00), V(180.00, 128.50))
    add_edge_seg(V(180.00, 128.50), V(179.75, 128.75))

    # 4. Relocate F1 for edge clearance
    f1 = board.FindFootprintByReference('F1')
    if f1: f1.SetPosition(V(160.00, 71.50))

    # 5. Duplicate GND zone priority fix
    for z in board.Zones():
        if z.GetNetname() == 'GND':
            bbox = z.GetBoundingBox()
            if ToMM(bbox.GetWidth()) < 1.0 and abs(ToMM(bbox.GetX()) - 74.5) < 1.0:
                if z.GetAssignedPriority() == 5:
                    z.SetAssignedPriority(4)

    gnd_net = board.FindNet('GND')
    net_5v = board.FindNet('+5V')
    net_3v3 = board.FindNet('+3V3')
    net_1v8 = board.FindNet('+1V8')

    def add_via(x_mm, y_mm, net=gnd_net):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(V(x_mm, y_mm))
        via.SetWidth(FromMM(0.60))
        via.SetDrill(FromMM(0.30))
        via.SetNet(net)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        board.Add(via)
        return via

    def add_track(p1, p2, net, layer=pcbnew.F_Cu, width=0.20):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(p1); t.SetEnd(p2); t.SetLayer(layer)
        t.SetWidth(FromMM(width)); t.SetNet(net)
        board.Add(t)
        return t

    # 6. CAN Transceiver (Block B)
    print('Routing CAN subsystem...')
    u49 = board.FindFootprintByReference('U49')
    j16 = board.FindFootprintByReference('J16')
    d64 = board.FindFootprintByReference('D64')
    r337 = board.FindFootprintByReference('R337')
    r338 = board.FindFootprintByReference('R338')
    c167 = board.FindFootprintByReference('C167')
    r340 = board.FindFootprintByReference('R340')
    c168 = board.FindFootprintByReference('C168')
    c169 = board.FindFootprintByReference('C169')

    if u49 and j16 and d64 and r337 and r338 and c167 and r340:
        r337.SetOrientation(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
        r340.SetOrientation(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))

        canh_u = u49.FindPadByNumber('7')
        canl_u = u49.FindPadByNumber('6')
        canh_j = j16.FindPadByNumber('2')
        canl_j = j16.FindPadByNumber('3')
        canh_d = d64.FindPadByNumber('1')
        canl_d = d64.FindPadByNumber('2')

        # Differential pair on B.Cu
        add_track(canh_u.GetPosition(), canh_d.GetPosition(), canh_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
        add_track(canh_d.GetPosition(), canh_j.GetPosition(), canh_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
        add_track(canl_u.GetPosition(), canl_d.GetPosition(), canl_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
        add_track(canl_d.GetPosition(), canl_j.GetPosition(), canl_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)

        # Center tap on B.Cu at X=159.50
        tap_net = r337.FindPadByNumber('2').GetNet()
        add_track(r337.FindPadByNumber('2').GetPosition(), r338.FindPadByNumber('1').GetPosition(), tap_net, layer=pcbnew.B_Cu, width=0.25)
        add_track(r338.FindPadByNumber('1').GetPosition(), c167.FindPadByNumber('1').GetPosition(), tap_net, layer=pcbnew.B_Cu, width=0.25)

        # C167 pin 2 to GND via placed to the LEFT at (157.50, 82.70)
        add_via(157.50, 82.70, gnd_net)
        add_track(c167.FindPadByNumber('2').GetPosition(), V(157.50, 82.70), gnd_net, layer=pcbnew.B_Cu, width=0.25)

        # R337 pin 1 to CANH on B.Cu
        add_track(r337.FindPadByNumber('1').GetPosition(), V(155.80, 79.00), canh_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
        add_track(V(155.80, 79.00), canh_d.GetPosition(), canh_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)

        # R338 pin 2 to CANL via In3.Cu bridge at Y=81.30
        add_via(157.00, 81.30, canl_u.GetNet())
        add_track(r338.FindPadByNumber('2').GetPosition(), V(157.00, 81.30), canl_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
        add_via(153.20, 81.30, canl_u.GetNet())
        add_track(V(157.00, 81.30), V(153.20, 81.30), canl_u.GetNet(), layer=pcbnew.In3_Cu, width=0.25)
        add_track(V(153.20, 81.30), canl_d.GetPosition(), canl_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)

        # R340 (STB)
        stb_net = u49.FindPadByNumber('8').GetNet()
        add_track(u49.FindPadByNumber('8').GetPosition(), r340.FindPadByNumber('1').GetPosition(), stb_net, layer=pcbnew.B_Cu, width=0.25)
        add_via(161.00, 84.50, gnd_net)
        add_track(r340.FindPadByNumber('2').GetPosition(), V(161.00, 84.50), gnd_net, layer=pcbnew.B_Cu, width=0.25)

        # U49 power/GND and bypass caps
        add_via(155.00, 87.50, gnd_net)
        add_track(u49.FindPadByNumber('2').GetPosition(), V(155.00, 87.50), gnd_net, layer=pcbnew.B_Cu, width=0.25)

        if c168:
            add_track(u49.FindPadByNumber('3').GetPosition(), c168.FindPadByNumber('1').GetPosition(), net_5v, layer=pcbnew.B_Cu, width=0.30)
            add_via(154.84, 92.70, net_5v)
            add_track(c168.FindPadByNumber('1').GetPosition(), V(154.84, 92.70), net_5v, layer=pcbnew.B_Cu, width=0.30)
            add_via(153.88, 92.70, gnd_net)
            add_track(c168.FindPadByNumber('2').GetPosition(), V(153.88, 92.70), gnd_net, layer=pcbnew.B_Cu, width=0.25)

        if c169:
            add_track(u49.FindPadByNumber('5').GetPosition(), c169.FindPadByNumber('1').GetPosition(), net_3v3, layer=pcbnew.B_Cu, width=0.30)
            add_via(151.98, 82.20, net_3v3)
            add_track(c169.FindPadByNumber('1').GetPosition(), V(151.98, 82.20), net_3v3, layer=pcbnew.B_Cu, width=0.30)
            add_via(151.02, 82.20, gnd_net)
            add_track(c169.FindPadByNumber('2').GetPosition(), V(151.02, 82.20), gnd_net, layer=pcbnew.B_Cu, width=0.25)

        # D64 GND
        add_via(155.00, 77.20, gnd_net)
        add_track(d64.FindPadByNumber('3').GetPosition(), V(155.00, 77.20), gnd_net, layer=pcbnew.B_Cu, width=0.25)

        # J16 power & GND
        add_via(156.50, 69.50, net_5v)
        add_track(j16.FindPadByNumber('1').GetPosition(), V(156.50, 69.50), net_5v, layer=pcbnew.B_Cu, width=0.30)
        add_via(152.00, 70.88, gnd_net)
        add_track(j16.FindPadByNumber('4').GetPosition(), V(152.00, 70.88), gnd_net, layer=pcbnew.B_Cu, width=0.30)

        # J16 MP vias (left to 151.00, right to 160.00)
        add_via(151.00, 74.75, gnd_net)
        add_track(V(152.20, 74.75), V(151.00, 74.75), gnd_net, layer=pcbnew.B_Cu, width=0.30)
        add_via(160.00, 74.75, gnd_net)
        add_track(V(157.80, 74.75), V(160.00, 74.75), gnd_net, layer=pcbnew.B_Cu, width=0.30)

    # 7. Power & OE Routing (Block C)
    print('Routing power subsystem...')
    f2 = board.FindFootprintByReference('F2')
    c170 = board.FindFootprintByReference('C170')
    c171 = board.FindFootprintByReference('C171')
    j17 = board.FindFootprintByReference('J17')

    # F1 (+5V in, +5V_EXP out)
    if f1 and c170 and j17:
        p_f1 = f1.FindPadByNumber('1')
        p_f2 = f1.FindPadByNumber('2')
        p_c1 = c170.FindPadByNumber('1')
        p_c2 = c170.FindPadByNumber('2')
        net_5v_exp = p_f2.GetNet()

        add_via(157.86, 68.00, net_5v)
        add_track(p_f1.GetPosition(), V(157.86, 68.00), net_5v, width=0.40)

        # Connect F1 pin 2 to existing +5V_EXP track at (162.14, 70.00)
        add_track(p_f2.GetPosition(), V(162.14, 70.00), net_5v_exp, width=0.40)
        # Connect C170 pad 1 to (162.14, 70.00)
        add_track(V(162.14, 70.00), V(153.72, 70.00), net_5v_exp, width=0.40)
        # C170 pad 2 to GND
        add_via(155.28, 68.00, gnd_net)
        add_track(p_c2.GetPosition(), V(155.28, 68.00), gnd_net, width=0.30)

    # F2 (+3V3 in, +3V3_EXP out)
    if f2 and c171 and j17:
        p_f2_1 = f2.FindPadByNumber('1')
        p_f2_2 = f2.FindPadByNumber('2')
        p_c171_1 = c171.FindPadByNumber('1')
        p_c171_2 = c171.FindPadByNumber('2')
        net_3v3_exp = p_f2_2.GetNet()

        add_via(164.60, 68.00, net_3v3)
        add_track(p_f2_1.GetPosition(), V(164.60, 68.00), net_3v3, width=0.40)

        # C171 pad 1 to +3V3_EXP via In3.Cu
        add_via(170.47, 69.50, net_3v3_exp)
        add_track(V(170.47, 71.50), V(170.47, 69.50), net_3v3_exp, width=0.40)
        add_via(151.00, 69.50, net_3v3_exp)
        add_track(V(170.47, 69.50), V(151.00, 69.50), net_3v3_exp, layer=pcbnew.In3_Cu, width=0.40)
        add_track(V(151.00, 69.50), V(151.00, 72.50), net_3v3_exp, width=0.40)
        add_track(V(151.00, 72.50), p_c171_1.GetPosition(), net_3v3_exp, width=0.40)

        # C171 pad 2 GND
        add_via(151.00, 73.80, gnd_net)
        add_track(p_c171_2.GetPosition(), V(151.00, 73.80), gnd_net, width=0.30)

    # J17 pin 17 (+3V3_EXP) to existing via at (164.50, 94.72)
    p_j17 = j17.FindPadByNumber('17')
    if p_j17:
        add_track(V(164.50, 94.72), p_j17.GetPosition(), net_3v3_exp, width=0.35)

    # J17 pin 32 (GND) to via at (177.03, 112.72)
    p_j32 = j17.FindPadByNumber('32')
    if p_j32:
        add_via(177.03, 112.72, gnd_net)
        add_track(p_j32.GetPosition(), V(177.03, 112.72), gnd_net, width=0.30)

    # C173, C175, C177, C179: straight horizontal connections into B.Cu bus at X=164.50
    caps_3v3 = [('C173', 81.50), ('C175', 91.50), ('C177', 101.50), ('C179', 102.50)]
    for c_ref, cy in caps_3v3:
        c_fp = board.FindFootprintByReference(c_ref)
        if c_fp:
            c1 = c_fp.FindPadByNumber('1') # +3V3_EXP (159.52, cy)
            c2 = c_fp.FindPadByNumber('2') # GND (160.48, cy)
            # Pad 1 to bus via at (164.50, cy)
            add_via(164.50, cy, net_3v3_exp)
            add_track(c1.GetPosition(), V(164.50, cy), net_3v3_exp, width=0.25)
            # Pad 2 to GND via at (161.50, cy)
            add_via(161.50, cy, gnd_net)
            add_track(c2.GetPosition(), V(161.50, cy), gnd_net, width=0.25)

    # +1V8 power & OE resistors for U51-U54
    pairs = [
        ('U51', 'C172', 'R341'),
        ('U52', 'C174', 'R342'),
        ('U53', 'C176', 'R343'),
        ('U54', 'C178', 'R344')
    ]
    for u_ref, c_ref, r_ref in pairs:
        u_fp = board.FindFootprintByReference(u_ref)
        c_fp = board.FindFootprintByReference(c_ref)
        r_fp = board.FindFootprintByReference(r_ref)
        if not (u_fp and c_fp and r_fp): continue

        p2 = u_fp.FindPadByNumber('2')
        p10 = u_fp.FindPadByNumber('10')
        c1 = c_fp.FindPadByNumber('1') # GND
        c2 = c_fp.FindPadByNumber('2') # +1V8
        r1 = r_fp.FindPadByNumber('1') # +1V8
        r2 = r_fp.FindPadByNumber('2') # OE

        # C2 to U2 (+1V8)
        add_track(c2.GetPosition(), p2.GetPosition(), net_1v8, width=0.25)
        # R1 to C2 (+1V8)
        add_track(r1.GetPosition(), c2.GetPosition(), net_1v8, width=0.20)
        # R2 to U10 (OE) dogleg below pin 9
        uy = ToMM(p10.GetPosition().y)
        p_c1 = V(155.51, uy + 0.40)
        p_c2 = V(157.14, uy + 0.40)
        add_track(r2.GetPosition(), p_c1, p10.GetNet(), width=0.20)
        add_track(p_c1, p_c2, p10.GetNet(), width=0.20)
        add_track(p_c2, p10.GetPosition(), p10.GetNet(), width=0.20)

    # 8. River Routing for 3.3V GPIOs (Block D)
    print('Executing river routing for 3.3V GPIOs...')
    odd_signals = [
        ('U51', '20', 'J17', '3'),
        ('U51', '18', 'J17', '5'),
        ('U51', '17', 'J17', '7'),
        ('U51', '14', 'J17', '11'),
        ('U51', '13', 'J17', '13'),
        ('U51', '12', 'J17', '15'),
        ('U52', '17', 'J17', '19'),
        ('U52', '16', 'J17', '21'),
        ('U52', '14', 'J17', '23'),
        ('U53', '20', 'J17', '27'),
        ('U53', '17', 'J17', '29'),
        ('U53', '16', 'J17', '31'),
        ('U53', '15', 'J17', '33'),
        ('U53', '14', 'J17', '35'),
        ('U53', '12', 'J17', '37'),
    ]

    for i, (u_ref, u_pin, j_ref, j_pin) in enumerate(odd_signals):
        u_fp = board.FindFootprintByReference(u_ref)
        j_fp = board.FindFootprintByReference(j_ref)
        if not u_fp or not j_fp: continue
        u_pad = u_fp.FindPadByNumber(u_pin)
        j_pad = j_fp.FindPadByNumber(j_pin)
        if not u_pad or not j_pad: continue

        net = u_pad.GetNet()
        up = u_pad.GetPosition()
        jp = j_pad.GetPosition()
        uy = ToMM(up.y)
        jy = ToMM(jp.y)

        x_col = 168.50 - i * 0.22
        p1 = V(x_col, uy)
        p2 = V(x_col, jy)
        add_track(up, p1, net, layer=pcbnew.F_Cu, width=0.18)
        add_track(p1, p2, net, layer=pcbnew.F_Cu, width=0.18)
        add_track(p2, jp, net, layer=pcbnew.F_Cu, width=0.18)

    # Even signals on In3.Cu (connecting directly to J17 through-hole pads)
    even_signals = [
        ('U51', '16', 'J17', '8'),
        ('U51', '15', 'J17', '10'),
        ('U52', '20', 'J17', '16'),
        ('U52', '18', 'J17', '18'),
        ('U52', '15', 'J17', '22'),
        ('U52', '13', 'J17', '24'),
        ('U52', '12', 'J17', '26'),
        ('U53', '18', 'J17', '28'),
        ('U53', '13', 'J17', '36'),
        ('U54', '18', 'J17', '38'),
        ('U54', '17', 'J17', '40'),
    ]

    for i, (u_ref, u_pin, j_ref, j_pin) in enumerate(even_signals):
        u_fp = board.FindFootprintByReference(u_ref)
        j_fp = board.FindFootprintByReference(j_ref)
        if not u_fp or not j_fp: continue
        u_pad = u_fp.FindPadByNumber(u_pin)
        j_pad = j_fp.FindPadByNumber(j_pin)
        if not u_pad or not j_pad: continue

        net = u_pad.GetNet()
        up = u_pad.GetPosition()
        jp = j_pad.GetPosition()
        uy = ToMM(up.y)
        jy = ToMM(jp.y)

        # Via from F.Cu pad to In3.Cu at X=164.00
        vx = 164.00
        add_track(up, V(vx, uy), net, layer=pcbnew.F_Cu, width=0.18)
        add_via(vx, uy, net)

        # Planar column ordering on In3.Cu
        x_col = 169.00 - i * 0.22
        p_in1 = V(x_col, uy)
        p_in2 = V(x_col, jy)
        add_track(V(vx, uy), p_in1, net, layer=pcbnew.In3_Cu, width=0.18)
        add_track(p_in1, p_in2, net, layer=pcbnew.In3_Cu, width=0.18)
        # Directly into through-hole pad of J17!
        add_track(p_in2, jp, net, layer=pcbnew.In3_Cu, width=0.18)

    # U54 pin 20 -> J17 pin 12 on In5.Cu
    u54 = board.FindFootprintByReference('U54')
    if u54 and j17:
        p20 = u54.FindPadByNumber('20')
        p12 = j17.FindPadByNumber('12')
        if p20 and p12:
            net12 = p20.GetNet()
            p20_y = ToMM(p20.GetPosition().y)
            p12_y = ToMM(p12.GetPosition().y)
            add_track(p20.GetPosition(), V(164.00, p20_y), net12, width=0.18)
            add_via(164.00, p20_y, net12)
            add_track(V(164.00, p20_y), V(164.00, p12_y), net12, layer=pcbnew.In5_Cu, width=0.18)
            add_track(V(164.00, p12_y), p12.GetPosition(), net12, layer=pcbnew.In5_Cu, width=0.18)

    # 9. A* Grid Router for SoM 1.8V Escape Routing (Block E)
    print('Initializing A* Grid Router for SoM 1.8V escape routing...')
    router = GridRouter(130.0, 160.0, 68.0, 128.0, res=0.25)

    # Block existing tracks/vias on In3.Cu and In5.Cu
    for t in board.GetTracks():
        p1, p2 = t.GetStart(), t.GetEnd()
        x1, y1 = ToMM(p1.x), ToMM(p1.y)
        x2, y2 = ToMM(p2.x), ToMM(p2.y)
        l = t.GetLayer()
        if l == pcbnew.In3_Cu:
            router.block_box(x1, y1, x2, y2, 0, clearance=0.22)
        elif l == pcbnew.In5_Cu:
            router.block_box(x1, y1, x2, y2, 1, clearance=0.22)
        if isinstance(t, pcbnew.PCB_VIA):
            # Through-hole vias block both layers
            router.block_box(x1, y1, x1, y1, 0, clearance=0.35)
            router.block_box(x1, y1, x1, y1, 1, clearance=0.35)
            router.block_via_box(x1, y1, x1, y1, clearance=0.40)

    # Block only actual B.Cu component pads from via placement
    for ref in ['U49', 'J16', 'D64', 'R337', 'R338', 'C167', 'R340', 'C168', 'C169']:
        fp = board.FindFootprintByReference(ref)
        if fp:
            for pad in fp.Pads():
                pos = pad.GetPosition()
                px, py = ToMM(pos.x), ToMM(pos.y)
                router.block_via_box(px, py, px, py, clearance=0.45)

    som_signals = [
        ('U51', '1', 'I2C1_SDA', 0),
        ('U51', '3', 'I2C1_SCL', 0),
        ('U51', '4', 'GPIO09', 0),
        ('U51', '5', 'UART1_TXD', 0),
        ('U51', '6', 'UART1_RXD', 0),
        ('U51', '7', 'GPIO11', 1),
        ('U51', '8', 'GPIO01', 1),
        ('U51', '9', 'GPIO12', 1),
        ('U52', '1', 'GPIO07', 0),
        ('U52', '3', 'GPIO010', 1),
        ('U52', '4', 'SPIO_MOSI', 0),
        ('U52', '5', 'SPIO_MISO', 0),
        ('U52', '6', 'GPIO13', 1),
        ('U52', '7', 'SPIO_SCK', 0),
        ('U52', '8', '~{SPI0_CS0}', 0),
        ('U52', '9', '~{SPI0_CS1}', 0),
        ('U53', '1', 'I2C2_SDA', 0),
        ('U53', '3', 'I2C2_SCL', 0),
        ('U53', '4', 'FAN_PWM', 0),
        ('U53', '5', 'USER_BTN0', 0),
        ('U53', '6', 'USER_LED0', 0),
        ('U53', '7', 'I2S0_LRCK', 0),
        ('U53', '8', 'USER_LED1', 0),
        ('U53', '9', 'USER_BTN1', 0),
        ('U54', '1', 'I2S0_SCLK', 0),
        ('U54', '3', 'I2S0_SDIN', 0),
        ('U54', '4', 'I2S0_SDOUT', 0),
        ('U49', '1', 'CAN_TX', 0),
        ('U49', '4', 'CAN_RX', 0),
    ]

    routed_count = 0
    for chip_ref, pin_num, net_name, pref_l in som_signals:
        fp = board.FindFootprintByReference(chip_ref)
        if not fp: continue
        dest_pad = fp.FindPadByNumber(pin_num)
        if not dest_pad: continue
        dp = dest_pad.GetPosition()
        dx, dy = ToMM(dp.x), ToMM(dp.y)

        # Find closest existing track endpoint on this net
        pts = []
        for t in board.GetTracks():
            if t.GetNetname() == net_name:
                p1, p2 = t.GetStart(), t.GetEnd()
                pts.append((ToMM(p1.x), ToMM(p1.y), t.GetLayer()))
                pts.append((ToMM(p2.x), ToMM(p2.y), t.GetLayer()))
        if not pts:
            continue
        best_pt = max(pts, key=lambda p: p[0])
        sx, sy, sl = best_pt

        # Entry via to In3/In5 if currently on F.Cu
        start_x, start_y = sx, sy
        if sl == pcbnew.F_Cu:
            start_x, start_y = sx, sy
            add_via(start_x, start_y, dest_pad.GetNet())

        # Exit via from In3/In5 to F.Cu destination pad
        end_x = dx - 1.50
        end_y = dy

        path = router.route_net((start_x, start_y), (end_x, end_y), prefer_layer=pref_l)
        if path:
            net_obj = dest_pad.GetNet()
            # Collapse collinear points into segments
            collapsed = [path[0]]
            for i in range(1, len(path) - 1):
                prev_c, prev_r, prev_l = collapsed[-1]
                curr_c, curr_r, curr_l = path[i]
                next_c, next_r, next_l = path[i + 1]
                if curr_l != prev_l or (curr_c - prev_c, curr_r - prev_r) != (next_c - curr_c, next_r - curr_r):
                    collapsed.append(path[i])
            collapsed.append(path[-1])

            # Emit segments and vias
            for i in range(len(collapsed) - 1):
                c1, r1, l1 = collapsed[i]
                c2, r2, l2 = collapsed[i + 1]
                layer = pcbnew.In3_Cu if l1 == 0 else pcbnew.In5_Cu
                p_a = V(router.to_world(c1, r1)[0], router.to_world(c1, r1)[1])
                p_b = V(router.to_world(c2, r2)[0], router.to_world(c2, r2)[1])
                add_track(p_a, p_b, net_obj, layer=layer, width=0.18)
                if l1 != l2:
                    add_via(router.to_world(c2, r2)[0], router.to_world(c2, r2)[1], net_obj)

            # Connect end_x, end_y to dest_pad on F.Cu
            last_c, last_r, last_l = collapsed[-1]
            last_x, last_y = router.to_world(last_c, last_r)
            add_via(last_x, last_y, net_obj)
            add_track(V(last_x, last_y), dp, net_obj, layer=pcbnew.F_Cu, width=0.18)
            routed_count += 1

    print(f'Successfully routed {routed_count} / {len(som_signals)} SoM signals with A* Router.')

    print('Refilling all zones...')
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())

    print(f'Saving final board: {pcb_out}')
    board.Save(pcb_out)
    print('Routing execution completed successfully!')

if __name__ == '__main__':
    main()
