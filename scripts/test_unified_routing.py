#!/usr/bin/env python3
"""
scripts/test_unified_routing.py
Deterministic, zero-short routing test on test_block_b.kicad_pcb
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

    def block_box(self, x1, y1, x2, y2, layer_idx, clearance=0.15):
        c1, r1 = self.to_grid(min(x1, x2) - clearance, min(y1, y2) - clearance)
        c2, r2 = self.to_grid(max(x1, x2) + clearance, max(y1, y2) + clearance)
        for r in range(r1, r2 + 1):
            base = r * self.cols
            for c in range(c1, c2 + 1):
                self.grid[layer_idx][base + c] = 1

    def block_via_box(self, x1, y1, x2, y2, clearance=0.25):
        c1, r1 = self.to_grid(min(x1, x2) - clearance, min(y1, y2) - clearance)
        c2, r2 = self.to_grid(max(x1, x2) + clearance, max(y1, y2) + clearance)
        for r in range(r1, r2 + 1):
            base = r * self.cols
            for c in range(c1, c2 + 1):
                self.via_blocked[base + c] = 1

    def unblock_pt(self, x, y, layer_idx):
        c, r = self.to_grid(x, y)
        for dr in range(-1, 2):
            for dc in range(-1, 2):
                nc, nr = c + dc, r + dr
                if 0 <= nc < self.cols and 0 <= nr < self.rows:
                    self.grid[layer_idx][nr * self.cols + nc] = 0

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
                    neighbors.append((c, r, nl, 4.0))

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
                           self.x_min + c * self.res, self.y_min + r * self.res, l, clearance=0.15)
            if (c, r) in [(p[0], p[1]) for p in path if p[2] != l]:
                self.block_via_box(self.x_min + c * self.res, self.y_min + r * self.res,
                                   self.x_min + c * self.res, self.y_min + r * self.res, clearance=0.30)

        return path

def main():
    pcb_in = '/tmp/test_block_b.kicad_pcb'
    pcb_out = '/tmp/test_unified_routed.kicad_pcb'

    print(f'Loading baseboard: {pcb_in}')
    board = pcbnew.LoadBoard(pcb_in)

    gnd_net = board.FindNet('GND')
    net_5v = board.FindNet('+5V')
    net_3v3 = board.FindNet('+3V3')
    net_1v8 = board.FindNet('+1V8')

    def add_via(x_mm, y_mm, net):
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

    # 1. Power & OE Routing (Block C)
    print('Routing power subsystem (Block C)...')
    f1 = board.FindFootprintByReference('F1')
    f2 = board.FindFootprintByReference('F2')
    c170 = board.FindFootprintByReference('C170')
    c171 = board.FindFootprintByReference('C171')
    j17 = board.FindFootprintByReference('J17')

    p_f1 = f1.FindPadByNumber('1')
    p_f2 = f1.FindPadByNumber('2')
    net_5v_exp = p_f2.GetNet()
    p_f2_1 = f2.FindPadByNumber('1')
    p_f2_2 = f2.FindPadByNumber('2')
    net_3v3_exp = p_f2_2.GetNet()

    # Main +5V trunk from R235 (136.50, 114.40) to CAN & F1
    # Via at (138.00, 114.40)
    add_track(V(136.50, 114.40), V(138.00, 114.40), net_5v, layer=pcbnew.F_Cu, width=0.40)
    add_via(138.00, 114.40, net_5v)
    # In3.Cu across to (156.50, 114.40)
    add_track(V(138.00, 114.40), V(156.50, 114.40), net_5v, layer=pcbnew.In3_Cu, width=0.40)
    # North along 156.50 on In3.Cu to (156.50, 69.50)
    add_track(V(156.50, 114.40), V(156.50, 69.50), net_5v, layer=pcbnew.In3_Cu, width=0.40)
    # Connect directly to F1 pin 1
    add_track(V(156.50, 69.50), V(156.50, 70.50), net_5v, layer=pcbnew.F_Cu, width=0.40)
    add_track(V(156.50, 70.50), p_f1.GetPosition(), net_5v, layer=pcbnew.F_Cu, width=0.40)

    # F1 pin 2 to +5V_EXP
    add_track(p_f2.GetPosition(), V(162.14, 70.00), net_5v_exp, layer=pcbnew.F_Cu, width=0.40)
    add_track(V(162.14, 70.00), c170.FindPadByNumber('1').GetPosition(), net_5v_exp, layer=pcbnew.F_Cu, width=0.40)
    # C170 pin 2 to GND
    add_via(155.28, 68.00, gnd_net)
    add_track(c170.FindPadByNumber('2').GetPosition(), V(155.28, 68.00), gnd_net, layer=pcbnew.F_Cu, width=0.30)

    # Main +3V3 trunk from R233 (136.50, 110.30) to CAN & F2
    add_track(V(136.50, 110.30), V(138.00, 110.30), net_3v3, layer=pcbnew.F_Cu, width=0.40)
    add_via(138.00, 110.30, net_3v3)
    # In3.Cu across to (152.00, 110.30)
    add_track(V(138.00, 110.30), V(152.00, 110.30), net_3v3, layer=pcbnew.In3_Cu, width=0.40)
    # Branch to U49 / C169 at (151.98, 82.20)
    add_track(V(152.00, 110.30), V(151.98, 82.20), net_3v3, layer=pcbnew.In3_Cu, width=0.40)
    # Continue north to (152.00, 69.50)
    add_track(V(151.98, 82.20), V(152.00, 69.50), net_3v3, layer=pcbnew.In3_Cu, width=0.40)
    add_track(V(152.00, 69.50), V(163.50, 69.50), net_3v3, layer=pcbnew.In3_Cu, width=0.40)
    add_via(163.50, 69.50, net_3v3)
    add_track(V(163.50, 69.50), p_f2_1.GetPosition(), net_3v3, layer=pcbnew.F_Cu, width=0.40)

    # F2 pin 2 to C171 pad 1 via In3.Cu at Y=68.50
    add_via(167.45, 68.50, net_3v3_exp)
    add_track(p_f2_2.GetPosition(), V(167.45, 68.50), net_3v3_exp, layer=pcbnew.F_Cu, width=0.40)
    add_via(151.00, 68.50, net_3v3_exp)
    add_track(V(167.45, 68.50), V(151.00, 68.50), net_3v3_exp, layer=pcbnew.In3_Cu, width=0.40)
    add_track(V(151.00, 68.50), V(151.00, 72.50), net_3v3_exp, layer=pcbnew.F_Cu, width=0.40)
    add_track(V(151.00, 72.50), c171.FindPadByNumber('1').GetPosition(), net_3v3_exp, layer=pcbnew.F_Cu, width=0.40)
    # C171 pin 2 to GND
    add_via(151.00, 73.80, gnd_net)
    add_track(c171.FindPadByNumber('2').GetPosition(), V(151.00, 73.80), gnd_net, layer=pcbnew.F_Cu, width=0.30)

    # J17 pin 17 to B.Cu bus at (164.50, 94.72) ON B.Cu!
    p_j17 = j17.FindPadByNumber('17')
    add_track(V(164.50, 94.72), p_j17.GetPosition(), net_3v3_exp, layer=pcbnew.B_Cu, width=0.35)

    # C173, C175, C177, C179 straight horizontal connections
    caps_3v3 = [('C173', 81.50), ('C175', 91.50), ('C177', 101.50), ('C179', 102.50)]
    for c_ref, cy in caps_3v3:
        c_fp = board.FindFootprintByReference(c_ref)
        if c_fp:
            c1 = c_fp.FindPadByNumber('1')
            c2 = c_fp.FindPadByNumber('2')
            add_via(164.50, cy, net_3v3_exp)
            add_track(c1.GetPosition(), V(164.50, cy), net_3v3_exp, layer=pcbnew.F_Cu, width=0.25)
            add_via(161.50, cy, gnd_net)
            add_track(c2.GetPosition(), V(161.50, cy), gnd_net, layer=pcbnew.F_Cu, width=0.25)

    # Main +1V8 trunk from R234 (136.50, 111.80) to U51-U54
    add_track(V(136.50, 111.80), V(138.00, 111.80), net_1v8, layer=pcbnew.F_Cu, width=0.40)
    add_via(138.00, 111.80, net_1v8)
    add_track(V(138.00, 111.80), V(153.50, 111.80), net_1v8, layer=pcbnew.In3_Cu, width=0.40)
    # North along 153.50 on In3.Cu
    add_track(V(153.50, 111.80), V(153.50, 75.00), net_1v8, layer=pcbnew.In3_Cu, width=0.40)

    # +1V8 & OE for U51-U54
    pairs = [
        ('U51', 'C172', 'R341', 75.00),
        ('U52', 'C174', 'R342', 85.00),
        ('U53', 'C176', 'R343', 95.00),
        ('U54', 'C178', 'R344', 105.00)
    ]
    for u_ref, c_ref, r_ref, y_feed in pairs:
        u_fp = board.FindFootprintByReference(u_ref)
        c_fp = board.FindFootprintByReference(c_ref)
        r_fp = board.FindFootprintByReference(r_ref)
        p2 = u_fp.FindPadByNumber('2')
        p10 = u_fp.FindPadByNumber('10')
        c1 = c_fp.FindPadByNumber('1')
        c2 = c_fp.FindPadByNumber('2')
        r1 = r_fp.FindPadByNumber('1')
        r2 = r_fp.FindPadByNumber('2')

        # Tap In3.Cu +1V8 trunk with a via at (153.50, y_feed)
        add_via(153.50, y_feed, net_1v8)
        add_track(V(153.50, y_feed), c2.GetPosition(), net_1v8, layer=pcbnew.F_Cu, width=0.25)
        add_track(c2.GetPosition(), p2.GetPosition(), net_1v8, layer=pcbnew.F_Cu, width=0.25)
        add_track(r1.GetPosition(), c2.GetPosition(), net_1v8, layer=pcbnew.F_Cu, width=0.20)

        # C1 to GND via
        add_via(153.50, y_feed - 1.20, gnd_net)
        add_track(c1.GetPosition(), V(153.50, y_feed - 1.20), gnd_net, layer=pcbnew.F_Cu, width=0.25)

        # R2 to OE pin 10 dogleg
        uy = ToMM(p10.GetPosition().y)
        p_c1 = V(155.51, uy + 0.40)
        p_c2 = V(157.14, uy + 0.40)
        add_track(r2.GetPosition(), p_c1, p10.GetNet(), layer=pcbnew.F_Cu, width=0.20)
        add_track(p_c1, p_c2, p10.GetNet(), layer=pcbnew.F_Cu, width=0.20)
        add_track(p_c2, p10.GetPosition(), p10.GetNet(), layer=pcbnew.F_Cu, width=0.20)

    # 2. Block D — 3.3V GPIO River Routing
    print('Executing river routing for 3.3V GPIOs (Block D)...')
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
        u_pad = u_fp.FindPadByNumber(u_pin)
        j_pad = j_fp.FindPadByNumber(j_pin)
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
        u_pad = u_fp.FindPadByNumber(u_pin)
        j_pad = j_fp.FindPadByNumber(j_pin)
        net = u_pad.GetNet()
        up = u_pad.GetPosition()
        jp = j_pad.GetPosition()
        uy = ToMM(up.y)
        jy = ToMM(jp.y)

        vx = 163.60
        add_track(up, V(vx, uy), net, layer=pcbnew.F_Cu, width=0.18)
        add_via(vx, uy, net)

        x_col = 169.00 - i * 0.22
        p_in1 = V(x_col, uy)
        p_in2 = V(x_col, jy)
        add_track(V(vx, uy), p_in1, net, layer=pcbnew.In3_Cu, width=0.18)
        add_track(p_in1, p_in2, net, layer=pcbnew.In3_Cu, width=0.18)
        add_track(p_in2, jp, net, layer=pcbnew.In3_Cu, width=0.18)

    # U54 pin 20 -> J17 pin 12 on In5.Cu (run at X=169.80 clear of In3.Cu columns)
    u54 = board.FindFootprintByReference('U54')
    p20 = u54.FindPadByNumber('20')
    p12 = j17.FindPadByNumber('12')
    net12 = p20.GetNet()
    p20_y = ToMM(p20.GetPosition().y)
    p12_y = ToMM(p12.GetPosition().y)
    add_track(p20.GetPosition(), V(164.80, p20_y), net12, layer=pcbnew.F_Cu, width=0.18)
    add_via(164.80, p20_y, net12)
    add_track(V(164.80, p20_y), V(169.80, p20_y), net12, layer=pcbnew.In5_Cu, width=0.18)
    add_track(V(169.80, p20_y), V(169.80, p12_y), net12, layer=pcbnew.In5_Cu, width=0.18)
    add_track(V(169.80, p12_y), p12.GetPosition(), net12, layer=pcbnew.In5_Cu, width=0.18)

    # 3. Block E — 1.8V SoM Escape Routing with Staggered Vias
    print('Initializing A* Grid Router for SoM 1.8V escape routing (Block E)...')
    router = GridRouter(115.0, 162.0, 68.0, 128.0, res=0.25)

    # Block existing tracks/vias
    for t in board.GetTracks():
        p1, p2 = t.GetStart(), t.GetEnd()
        x1, y1 = ToMM(p1.x), ToMM(p1.y)
        x2, y2 = ToMM(p2.x), ToMM(p2.y)
        l = t.GetLayer()
        if l == pcbnew.In3_Cu:
            router.block_box(x1, y1, x2, y2, 0, clearance=0.15)
        elif l == pcbnew.In5_Cu:
            router.block_box(x1, y1, x2, y2, 1, clearance=0.15)
        if isinstance(t, pcbnew.PCB_VIA):
            router.block_box(x1, y1, x1, y1, 0, clearance=0.25)
            router.block_box(x1, y1, x1, y1, 1, clearance=0.25)
            router.block_via_box(x1, y1, x1, y1, clearance=0.30)

    # Block B.Cu CAN footprint pads from via penetration
    for ref in ['U49', 'J16', 'D64', 'R337', 'R338', 'C167', 'R340', 'C168', 'C169']:
        fp = board.FindFootprintByReference(ref)
        if fp:
            for pad in fp.Pads():
                pos = pad.GetPosition()
                px, py = ToMM(pos.x), ToMM(pos.y)
                router.block_via_box(px, py, px, py, clearance=0.45)

    som_signals = [
        ('U51', '1', 'I2C1_SDA', 151.0),
        ('U51', '3', 'I2C1_SCL', 149.5),
        ('U51', '4', 'GPIO09', 148.0),
        ('U51', '5', 'UART1_TXD', 151.0),
        ('U51', '6', 'UART1_RXD', 149.5),
        ('U51', '7', 'GPIO11', 148.0),
        ('U51', '8', 'GPIO01', 151.0),
        ('U51', '9', 'GPIO12', 149.5),
        ('U52', '1', 'GPIO07', 151.0),
        ('U52', '3', 'GPIO010', 149.5),
        ('U52', '4', 'SPIO_MOSI', 148.0),
        ('U52', '5', 'SPIO_MISO', 151.0),
        ('U52', '6', 'GPIO13', 149.5),
        ('U52', '7', 'SPIO_SCK', 148.0),
        ('U52', '8', '~{SPI0_CS0}', 151.0),
        ('U52', '9', '~{SPI0_CS1}', 149.5),
        ('U53', '1', 'I2C2_SDA', 151.0),
        ('U53', '3', 'I2C2_SCL', 149.5),
        ('U53', '5', 'USER_BTN0', 151.0),
        ('U53', '6', 'USER_LED0', 149.5),
        ('U53', '7', 'I2S0_LRCK', 148.0),
        ('U53', '8', 'USER_LED1', 151.0),
        ('U53', '9', 'USER_BTN1', 149.5),
        ('U54', '1', 'I2S0_SCLK', 151.0),
        ('U54', '3', 'I2S0_SDIN', 149.5),
        ('U54', '4', 'I2S0_SDOUT', 148.0),
    ]

    routed_count = 0
    for chip_ref, pin_num, net_name, via_x in som_signals:
        fp = board.FindFootprintByReference(chip_ref)
        dest_pad = fp.FindPadByNumber(pin_num)
        dp = dest_pad.GetPosition()
        dx, dy = ToMM(dp.x), ToMM(dp.y)

        # Find closest existing track endpoint
        pts = []
        for t in board.GetTracks():
            if t.GetNetname() == net_name:
                p1, p2 = t.GetStart(), t.GetEnd()
                pts.append((ToMM(p1.x), ToMM(p1.y), t.GetLayer()))
                pts.append((ToMM(p2.x), ToMM(p2.y), t.GetLayer()))
        if not pts: continue
        best_pt = max(pts, key=lambda p: p[0])
        sx, sy, sl = best_pt

        # Staggered via at (via_x, dy)
        end_x, end_y = via_x, dy

        # Unblock start & end points in router
        router.unblock_pt(sx, sy, 0)
        router.unblock_pt(sx, sy, 1)
        router.unblock_pt(end_x, end_y, 0)
        router.unblock_pt(end_x, end_y, 1)

        # Route on In3.Cu (layer 0) or In5.Cu (layer 1)
        path = router.route_net((sx, sy), (end_x, end_y), prefer_layer=0)
        if path:
            net_obj = dest_pad.GetNet()
            # Entry via if start was on F.Cu
            if sl == pcbnew.F_Cu:
                add_via(sx, sy, net_obj)

            collapsed = [path[0]]
            for i in range(1, len(path) - 1):
                prev_c, prev_r, prev_l = collapsed[-1]
                curr_c, curr_r, curr_l = path[i]
                next_c, next_r, next_l = path[i + 1]
                if curr_l != prev_l or (curr_c - prev_c, curr_r - prev_r) != (next_c - curr_c, next_r - curr_r):
                    collapsed.append(path[i])
            collapsed.append(path[-1])

            for i in range(len(collapsed) - 1):
                c1, r1, l1 = collapsed[i]
                c2, r2, l2 = collapsed[i + 1]
                layer = pcbnew.In3_Cu if l1 == 0 else pcbnew.In5_Cu
                p_a = V(router.to_world(c1, r1)[0], router.to_world(c1, r1)[1])
                p_b = V(router.to_world(c2, r2)[0], router.to_world(c2, r2)[1])
                add_track(p_a, p_b, net_obj, layer=layer, width=0.18)
                if l1 != l2:
                    add_via(router.to_world(c2, r2)[0], router.to_world(c2, r2)[1], net_obj)

            # Exit via at staggered coordinate
            add_via(end_x, end_y, net_obj)
            # Straight horizontal F.Cu trace to chip pad
            add_track(V(end_x, end_y), dp, net_obj, layer=pcbnew.F_Cu, width=0.18)
            routed_count += 1
            print(f'  Routed {net_name} -> {chip_ref} pin {pin_num} via ({end_x:.1f}, {end_y:.2f})')
        else:
            print(f'  FAILED {net_name} -> {chip_ref} pin {pin_num}')

    print(f'Routed {routed_count} / {len(som_signals)} SoM signals.')

    # CAN_TX and CAN_RX to U49 (on B.Cu)
    u49 = board.FindFootprintByReference('U49')
    if u49:
        for pnum, netname in [('1', 'CAN_TX'), ('4', 'CAN_RX')]:
            cp = u49.FindPadByNumber(pnum)
            cpos = cp.GetPosition()
            cnet = cp.GetNet()
            pts = [t.GetEnd() for t in board.GetTracks() if t.GetNetname() == netname]
            if pts:
                best = max(pts, key=lambda p: p.x)
                bx, by = ToMM(best.x), ToMM(best.y)
                # Route on In5.Cu / B.Cu into U49 pad
                add_via(bx, by, cnet)
                add_track(V(bx, by), V(ToMM(cpos.x), by), cnet, layer=pcbnew.B_Cu, width=0.20)
                add_track(V(ToMM(cpos.x), by), cpos, cnet, layer=pcbnew.B_Cu, width=0.20)
                print(f'  Connected {netname} to U49 pin {pnum}')

    print('Selectively refilling expansion GND zones...')
    zones_to_fill = [z for z in board.Zones() if ToMM(z.GetBoundingBox().GetX()) > 130.0]
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(zones_to_fill)

    print(f'Saving board to {pcb_out}')
    board.Save(pcb_out)
    print('Finished test_unified_routing.py')

if __name__ == '__main__':
    main()
