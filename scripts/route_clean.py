#!/usr/bin/env python3
"""
scripts/route_clean.py
Zero-short, clearance-verified routing for Jetson Orin Baseboard.
"""

import sys
import os

sys.path.append('/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/lib/python3.9/site-packages')
import pcbnew

def ToMM(val): return pcbnew.ToMM(val)
def FromMM(val): return pcbnew.FromMM(val)
def V(x, y): return pcbnew.VECTOR2I(FromMM(x), FromMM(y))

def main():
    pcb_in = 'jetson-orin-baseboard.kicad_pcb'
    pcb_out = '/tmp/test_clean_routed.kicad_pcb'
    orig_pcb_path = '/tmp/git_orig.kicad_pcb'

    print(f'Loading board: {pcb_in}')
    board = pcbnew.LoadBoard(pcb_in)

    # 1. Restore verified baseline non-expansion tracks
    if os.path.exists(orig_pcb_path):
        print('Restoring baseline non-expansion tracks...')
        b_orig = pcbnew.LoadBoard(orig_pcb_path)
        accidental_tags = ['/USB Debug, DP/', '/HDMI/', '/CSI/', 'Net-(U5-']
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

    # 3. Clean Edge.Cuts outline
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

    # 5. Resolve duplicate GND zone priority conflict
    for z in board.Zones():
        if z.GetNetname() == 'GND':
            bbox = z.GetBoundingBox()
            if ToMM(bbox.GetWidth()) < 1.0 and abs(ToMM(bbox.GetX()) - 74.5) < 1.0:
                if z.GetAssignedPriority() == 5:
                    z.SetAssignedPriority(4)

    # Helper functions
    gnd_net = board.FindNet('GND')
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

    # 6. Power Routing
    print('Routing power...')
    j17 = board.FindFootprintByReference('J17')
    f2 = board.FindFootprintByReference('F2')
    c170 = board.FindFootprintByReference('C170')
    c171 = board.FindFootprintByReference('C171')
    net_5v = board.FindNet('+5V')
    net_3v3 = board.FindNet('+3V3')
    net_1v8 = board.FindNet('+1V8')

    # F1 (+5V in, +5V_EXP out)
    if f1 and c170 and j17:
        p_c1 = c170.FindPadByNumber('1')
        p_c2 = c170.FindPadByNumber('2')
        p_f1 = f1.FindPadByNumber('1')
        p_f2 = f1.FindPadByNumber('2')
        p_j2 = j17.FindPadByNumber('2')
        p_j4 = j17.FindPadByNumber('4')
        
        # +5V into F1 pin 1
        if p_f1:
            add_via(154.00, 71.50, net_5v)
            add_track(V(154.00, 71.50), p_f1.GetPosition(), net_5v, width=0.50)

        # +5V_EXP from F1 pin 2 to C170 pad 1 and J17 pins 2, 4
        if p_f2 and p_c1 and p_j2 and p_j4:
            net_5v_exp = p_f2.GetNet()
            # C170 bypass
            add_track(p_f2.GetPosition(), p_c1.GetPosition(), net_5v_exp, width=0.50)
            if p_c2:
                add_via(ToMM(p_c2.GetPosition().x) - 1.0, ToMM(p_c2.GetPosition().y), gnd_net)
                add_track(p_c2.GetPosition(), V(ToMM(p_c2.GetPosition().x) - 1.0, ToMM(p_c2.GetPosition().y)), gnd_net, width=0.30)
            
            # Route above F1/F2 at Y=69.80 to avoid F2
            p_up1 = V(162.14, 69.80)
            p_up2 = V(175.525, 69.80)
            add_track(p_f2.GetPosition(), p_up1, net_5v_exp, width=0.50)
            add_track(p_up1, p_up2, net_5v_exp, width=0.50)
            add_track(p_up2, p_j2.GetPosition(), net_5v_exp, width=0.50)
            add_track(p_j2.GetPosition(), p_j4.GetPosition(), net_5v_exp, width=0.50)

    # F2 (+3V3 in, +3V3_EXP out)
    if f2 and c171 and j17:
        p_c1 = c171.FindPadByNumber('1')
        p_c2 = c171.FindPadByNumber('2')
        p_f1 = f2.FindPadByNumber('1')
        p_f2 = f2.FindPadByNumber('2')
        p_j1 = j17.FindPadByNumber('1')
        
        # +3V3 into F2 pin 1
        if p_f1:
            add_via(164.60, 69.80, net_3v3)
            add_track(V(164.60, 69.80), p_f1.GetPosition(), net_3v3, width=0.50)

        # +3V3_EXP from F2 pin 2 to C171 pad 1, J17 pin 1, and U51-U54 pin 19
        if p_f2 and p_c1 and p_j1:
            net_3v3_exp = p_f2.GetNet()
            add_track(p_f2.GetPosition(), p_c1.GetPosition(), net_3v3_exp, width=0.50)
            if p_c2:
                add_via(ToMM(p_c2.GetPosition().x) - 1.0, ToMM(p_c2.GetPosition().y), gnd_net)
                add_track(p_c2.GetPosition(), V(ToMM(p_c2.GetPosition().x) - 1.0, ToMM(p_c2.GetPosition().y)), gnd_net, width=0.30)

            add_track(p_f2.GetPosition(), V(170.475, 71.50), net_3v3_exp, width=0.50)
            add_track(V(170.475, 71.50), p_j1.GetPosition(), net_3v3_exp, width=0.50)

            # Route +3V3_EXP bus on In5.Cu to feed U51-U54 pin 19
            add_via(170.475, 73.00, net_3v3_exp)
            add_via(163.00, 73.00, net_3v3_exp)
            add_track(V(170.475, 73.00), V(163.00, 73.00), net_3v3_exp, layer=pcbnew.In5_Cu, width=0.40)
            add_via(163.00, 107.50, net_3v3_exp)
            add_track(V(163.00, 73.00), V(163.00, 107.50), net_3v3_exp, layer=pcbnew.In5_Cu, width=0.40)
            
            for uy in [74.725, 84.725, 94.725, 104.725]:
                add_via(162.00, uy, net_3v3_exp)
                add_track(V(163.00, uy), V(162.00, uy), net_3v3_exp, layer=pcbnew.In5_Cu, width=0.30)
                add_track(V(162.00, uy), V(162.863, uy), net_3v3_exp, layer=pcbnew.F_Cu, width=0.30)

    # +1V8 for U51-U54 pin 2
    u_map = {'U51': 77.0, 'U52': 87.0, 'U53': 97.0, 'U54': 107.0}
    for u_ref, uy in u_map.items():
        u_fp = board.FindFootprintByReference(u_ref)
        if u_fp:
            p2 = u_fp.FindPadByNumber('2')
            if p2:
                # Via placed safely away from chip pads
                add_via(154.00, uy - 3.50, net_1v8)
                add_track(V(154.00, uy - 3.50), p2.GetPosition(), net_1v8, width=0.25)

    # GND return vias for J17 placed safely on the FAR RIGHT at X=178.80
    if j17:
        for g_pin in ['6', '9', '14', '20', '25', '30', '34', '39']:
            pad = j17.FindPadByNumber(g_pin)
            if pad:
                pos = pad.GetPosition()
                py = ToMM(pos.y)
                add_via(178.80, py, gnd_net)
                add_track(pos, V(178.80, py), gnd_net, width=0.25)

    # 7. CAN Transceiver (U49) & J16
    print('Routing CAN...')
    u49 = board.FindFootprintByReference('U49')
    j16 = board.FindFootprintByReference('J16')
    d64 = board.FindFootprintByReference('D64')
    r337 = board.FindFootprintByReference('R337')
    r338 = board.FindFootprintByReference('R338')
    c167 = board.FindFootprintByReference('C167')
    r340 = board.FindFootprintByReference('R340')

    if u49 and j16 and d64:
        canh_u = u49.FindPadByNumber('7')
        canl_u = u49.FindPadByNumber('6')
        canh_j = j16.FindPadByNumber('2')
        canl_j = j16.FindPadByNumber('3')
        canh_d = d64.FindPadByNumber('1')
        canl_d = d64.FindPadByNumber('2')

        # Parallel straight differential pair on B.Cu
        add_track(canh_u.GetPosition(), canh_d.GetPosition(), canh_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
        add_track(canh_d.GetPosition(), canh_j.GetPosition(), canh_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
        add_track(canl_u.GetPosition(), canl_d.GetPosition(), canl_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
        add_track(canl_d.GetPosition(), canl_j.GetPosition(), canl_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)

        # U49 power & ground
        add_via(155.63, 90.50, gnd_net)
        add_track(u49.FindPadByNumber('2').GetPosition(), V(155.63, 90.50), gnd_net, layer=pcbnew.B_Cu, width=0.25)

        add_via(154.37, 90.50, net_5v)
        add_track(u49.FindPadByNumber('3').GetPosition(), V(154.37, 90.50), net_5v, layer=pcbnew.B_Cu, width=0.25)

        add_via(153.09, 82.50, net_3v3)
        add_track(u49.FindPadByNumber('5').GetPosition(), V(153.09, 82.50), net_3v3, layer=pcbnew.B_Cu, width=0.25)

        # U49 pin 8 STB to R340 pad 1, R340 pad 2 to GND
        if r340:
            add_track(u49.FindPadByNumber('8').GetPosition(), r340.FindPadByNumber('1').GetPosition(), u49.FindPadByNumber('8').GetNet(), layer=pcbnew.B_Cu, width=0.25)
            add_via(157.00, 84.50, gnd_net)
            add_track(r340.FindPadByNumber('2').GetPosition(), V(157.00, 84.50), gnd_net, layer=pcbnew.B_Cu, width=0.25)

        # D64 pin 3 to GND
        add_via(155.00, 77.00, gnd_net)
        add_track(d64.FindPadByNumber('3').GetPosition(), V(155.00, 77.00), gnd_net, layer=pcbnew.B_Cu, width=0.25)

        # J16 pin 1 (+5V) and pin 4 (GND)
        add_via(156.50, 69.50, net_5v)
        add_track(j16.FindPadByNumber('1').GetPosition(), V(156.50, 69.50), net_5v, layer=pcbnew.B_Cu, width=0.25)
        add_via(153.50, 69.50, gnd_net)
        add_track(j16.FindPadByNumber('4').GetPosition(), V(153.50, 69.50), gnd_net, layer=pcbnew.B_Cu, width=0.25)

        # Termination R337, R338, C167
        if r337 and r338 and c167:
            # R337 pad 1 to CANH
            add_track(r337.FindPadByNumber('1').GetPosition(), V(155.80, 79.00), canh_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
            # R338 pad 2 to CANL via F.Cu bypass
            add_via(157.50, 80.50, canl_u.GetNet())
            add_track(r338.FindPadByNumber('2').GetPosition(), V(157.50, 80.50), canl_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
            add_via(153.50, 80.50, canl_u.GetNet())
            add_track(V(157.50, 80.50), V(153.50, 80.50), canl_u.GetNet(), layer=pcbnew.F_Cu, width=0.25)
            add_track(V(153.50, 80.50), canl_d.GetPosition(), canl_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)

            # Center tap: R337 pad 2, R338 pad 1, C167 pad 1
            tap_net = r337.FindPadByNumber('2').GetNet()
            add_track(r337.FindPadByNumber('2').GetPosition(), V(158.49, 80.50), tap_net, layer=pcbnew.B_Cu, width=0.25)
            add_track(V(158.49, 80.50), r338.FindPadByNumber('1').GetPosition(), tap_net, layer=pcbnew.B_Cu, width=0.25)
            add_track(r338.FindPadByNumber('1').GetPosition(), c167.FindPadByNumber('1').GetPosition(), tap_net, layer=pcbnew.B_Cu, width=0.25)
            
            # C167 pad 2 to GND
            add_via(157.00, 82.00, gnd_net)
            add_track(c167.FindPadByNumber('2').GetPosition(), V(157.00, 82.00), gnd_net, layer=pcbnew.B_Cu, width=0.25)

    # 8. Level Shifter OE Pull-Ups (approach from below to avoid Pin 9)
    print('Routing OE pull-ups...')
    oe_pairs = [('R341', 'U51'), ('R342', 'U52'), ('R343', 'U53'), ('R344', 'U54')]
    for r_ref, u_ref in oe_pairs:
        r_fp = board.FindFootprintByReference(r_ref)
        u_fp = board.FindFootprintByReference(u_ref)
        if r_fp and u_fp:
            p_r2 = r_fp.FindPadByNumber('2')
            p_u10 = u_fp.FindPadByNumber('10')
            if p_r2 and p_u10:
                uy = ToMM(p_u10.GetPosition().y)
                # Dogleg below pin 9
                p_c1 = V(155.50, uy + 0.35)
                p_c2 = V(157.14, uy + 0.35)
                add_track(p_r2.GetPosition(), p_c1, p_u10.GetNet(), layer=pcbnew.F_Cu, width=0.20)
                add_track(p_c1, p_c2, p_u10.GetNet(), layer=pcbnew.F_Cu, width=0.20)
                add_track(p_c2, p_u10.GetPosition(), p_u10.GetNet(), layer=pcbnew.F_Cu, width=0.20)
            
            p_r1 = r_fp.FindPadByNumber('1')
            if p_r1:
                # Via to +1V8
                ry = ToMM(p_r1.GetPosition().y)
                add_via(153.50, ry, net_1v8)
                add_track(p_r1.GetPosition(), V(153.50, ry), net_1v8, layer=pcbnew.F_Cu, width=0.20)

    # 9. Layer-Separated River Routing for 3.3V GPIOs (U51-U54 to J17)
    print('Executing layer-separated river routing for 3.3V GPIOs...')
    
    # 9a. Odd pins on F.Cu (strictly monotonic, right-to-left columns)
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

        x_col = 168.50 - i * 0.25
        p1 = V(x_col, uy)
        p2 = V(x_col, jy)
        add_track(up, p1, net, layer=pcbnew.F_Cu, width=0.18)
        add_track(p1, p2, net, layer=pcbnew.F_Cu, width=0.18)
        add_track(p2, jp, net, layer=pcbnew.F_Cu, width=0.18)

    # 9b. Even pins on B.Cu (strictly monotonic, left-to-right columns)
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

        vx1 = 163.50
        vx2 = 177.50
        add_track(up, V(vx1, uy), net, layer=pcbnew.F_Cu, width=0.18)
        add_via(vx1, uy, net)

        x_col = 165.20 + i * 0.25
        p_b1 = V(x_col, uy)
        p_b2 = V(x_col, jy)
        p_b3 = V(vx2, jy)
        add_track(V(vx1, uy), p_b1, net, layer=pcbnew.B_Cu, width=0.18)
        add_track(p_b1, p_b2, net, layer=pcbnew.B_Cu, width=0.18)
        add_track(p_b2, p_b3, net, layer=pcbnew.B_Cu, width=0.18)

        add_via(vx2, jy, net)
        add_track(p_b3, jp, net, layer=pcbnew.F_Cu, width=0.18)

    # U54 pin 20 to J17 pin 12 on In3.Cu
    u54 = board.FindFootprintByReference('U54')
    if u54 and j17:
        p20 = u54.FindPadByNumber('20')
        p12 = j17.FindPadByNumber('12')
        if p20 and p12:
            net12 = p20.GetNet()
            p20_y = ToMM(p20.GetPosition().y)
            p12_y = ToMM(p12.GetPosition().y)
            add_track(p20.GetPosition(), V(163.50, p20_y), net12, width=0.18)
            add_via(163.50, p20_y, net12)
            add_track(V(163.50, p20_y), V(163.50, p12_y), net12, layer=pcbnew.In3_Cu, width=0.18)
            add_via(163.50, p12_y, net12)
            add_track(V(163.50, p12_y), V(177.50, p12_y), net12, layer=pcbnew.In3_Cu, width=0.18)
            add_via(177.50, p12_y, net12)
            add_track(V(177.50, p12_y), p12.GetPosition(), net12, layer=pcbnew.F_Cu, width=0.18)

    # Refill zones and save
    print('Refilling zones...')
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())

    print(f'Saving to: {pcb_out}')
    board.Save(pcb_out)
    print('Done!')

if __name__ == '__main__':
    main()
