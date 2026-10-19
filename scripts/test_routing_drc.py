import sys
import os
import re

sys.path.append('/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/lib/python3.11/site-packages')
import pcbnew
sys.path.append('.'); from scripts.sync_pcb_netlist import parse_netlist

pcb_path = 'jetson-orin-baseboard.kicad_pcb'
net_path = 'jetson-orin-baseboard.net'

print(f'Loading board: {pcb_path}')
board = pcbnew.LoadBoard(pcb_path)
comp_nets, all_net_names = parse_netlist(net_path)

# Ensure nets
netinfo = board.GetNetInfo()
for net_name in all_net_names:
    item = netinfo.GetNetItem(net_name)
    if not item:
        new_item = pcbnew.NETINFO_ITEM(board, net_name)
        board.Add(new_item)

# 1. Update Edge.Cuts
edge_cuts = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
for d in edge_cuts:
    s = d.GetStart()
    e = d.GetEnd()
    sx, sy = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
    ex, ey = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
    if abs(sy - 68.75) < 0.1 and abs(ey - 68.75) < 0.1:
        if ex > 140.0: d.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(179.75), pcbnew.FromMM(68.75)))
    elif abs(sy - 68.75) < 0.1 and abs(ey - 69.00) < 0.1:
        d.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(179.75), pcbnew.FromMM(68.75)))
        d.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(180.00), pcbnew.FromMM(69.00)))
    elif sx > 145.0 and ex > 145.0 and abs(sx - ex) < 0.5:
        d.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(180.00), pcbnew.FromMM(69.00)))
        d.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(180.00), pcbnew.FromMM(128.50)))
    elif abs(sy - 128.50) < 0.1 and abs(ey - 128.75) < 0.1:
        d.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(180.00), pcbnew.FromMM(128.50)))
        d.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(179.75), pcbnew.FromMM(128.75)))
    elif abs(sy - 128.75) < 0.1 and abs(ey - 128.75) < 0.1:
        if sx > 140.0: d.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(179.75), pcbnew.FromMM(128.75)))

# 2. Depopulate defunct components
defunct_refs = ['J11', 'D39', 'D40', 'D45', 'D46', 'D49', 'D50', 
                'R100', 'R101', 'R102', 'R54', 'R64', 'R335', 'R121', 'R120', 'R336', 'C107', 'C114']
for d_ref in defunct_refs:
    fp = board.FindFootprintByReference(d_ref)
    if fp: board.Delete(fp)

# 3. Clean defunct and temporary tracks/vias
expansion_net_tags = ['_3V3', 'Expansion', 'Net-(U5', 'Net-(J18', 'Net-(U49', 'Net-(J16', 'USB_VBUS']
deleted_tracks = 0
for t in list(board.GetTracks()):
    name = t.GetNetname()
    if 'J11' in name or (name.startswith('/Peripherals/') and name.endswith('_CONN')) or any(tag in name for tag in expansion_net_tags):
        board.Delete(t)
        deleted_tracks += 1
print(f'Cleaned {deleted_tracks} defunct/expansion tracks.')

# 4. Standard footprint library directories
kicad_fp_dir = '/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints'
lib_hdr  = os.path.join(kicad_fp_dir, 'Connector_PinHeader_2.54mm.pretty')
lib_usb  = os.path.join(kicad_fp_dir, 'Connector_USB.pretty')
lib_so   = os.path.join(kicad_fp_dir, 'Package_SO.pretty')
lib_fuse = os.path.join(kicad_fp_dir, 'Fuse.pretty')
lib_sot  = os.path.join(kicad_fp_dir, 'Package_TO_SOT_SMD.pretty')
lib_cap  = os.path.join(kicad_fp_dir, 'Capacitor_SMD.pretty')
lib_res  = os.path.join(kicad_fp_dir, 'Resistor_SMD.pretty')

ref_tsot  = board.FindFootprintByReference('U28')
ref_tvs   = board.FindFootprintByReference('D16')
ref_jst   = board.FindFootprintByReference('J14')

def make_clone(template_fp, ref, val):
    fp = pcbnew.Cast_to_FOOTPRINT(template_fp.Duplicate(False))
    fp.SetReference(ref); fp.SetValue(val); return fp

def make_cap(ref, val, pkg='0402'):
    if pkg == '0402': fp = pcbnew.FootprintLoad(lib_cap, 'C_0402_1005Metric')
    elif pkg == '0603': fp = pcbnew.FootprintLoad(lib_cap, 'C_0603_1608Metric')
    elif pkg == '0805': fp = pcbnew.FootprintLoad(lib_cap, 'C_0805_2012Metric')
    fp.SetReference(ref); fp.SetValue(val); return fp

def make_res(ref, val, pkg='0402'):
    fp = pcbnew.FootprintLoad(lib_res, 'R_0402_1005Metric')
    fp.SetReference(ref); fp.SetValue(val); return fp

placements = {}
j17 = pcbnew.FootprintLoad(lib_hdr, 'PinHeader_2x20_P2.54mm_Vertical_SMD')
j17.SetReference('J17'); j17.SetValue('Conn_02x20_Odd_Even')
placements['J17'] = (j17, 173.00, 98.75, 0.0, pcbnew.F_Cu)

u_y_map = {'U51': 77.0, 'U52': 87.0, 'U53': 97.0, 'U54': 107.0}
for ref, y_pos in u_y_map.items():
    u_fp = pcbnew.FootprintLoad(lib_so, 'TSSOP-20_4.4x6.5mm_P0.65mm')
    u_fp.SetReference(ref); u_fp.SetValue('TXS0108EPW')
    placements[ref] = (u_fp, 160.00, y_pos, 0.0, pcbnew.F_Cu)

c_pairs = [('C172', 'C173', 'U51'), ('C174', 'C175', 'U52'), 
           ('C176', 'C177', 'U53')]
for ca_ref, cb_ref, u_ref in c_pairs:
    uy = u_y_map[u_ref]
    placements[ca_ref] = (make_cap(ca_ref, '100nF', '0402'), 155.00, uy - 2.0, 0.0, pcbnew.F_Cu)
    placements[cb_ref] = (make_cap(cb_ref, '100nF', '0402'), 160.00, uy + 4.5, 0.0, pcbnew.F_Cu)

placements['C178'] = (make_cap('C178', '100nF', '0402'), 154.00, 105.00, 0.0, pcbnew.F_Cu)
placements['C179'] = (make_cap('C179', '100nF', '0402'), 154.00, 107.00, 0.0, pcbnew.F_Cu)
placements['R344'] = (make_res('R344', '10k', '0402'), 154.00, 109.00, 0.0, pcbnew.F_Cu)

for r_ref, u_ref in [('R341', 'U51'), ('R342', 'U52'), ('R343', 'U53')]:
    uy = u_y_map[u_ref]
    placements[r_ref] = (make_res(r_ref, '10k', '0402'), 155.00, uy + 2.0, 0.0, pcbnew.F_Cu)

f1 = pcbnew.FootprintLoad(lib_fuse, 'Fuse_1812_4532Metric')
f1.SetReference('F1'); f1.SetValue('1.1A')
placements['F1'] = (f1, 160.00, 70.50, 0.0, pcbnew.F_Cu)

f2 = pcbnew.FootprintLoad(lib_fuse, 'Fuse_1206_3216Metric')
f2.SetReference('F2'); f2.SetValue('0.75A')
placements['F2'] = (f2, 166.00, 70.50, 0.0, pcbnew.F_Cu)

placements['C170'] = (make_cap('C170', '10uF', '0603'), 154.50, 70.00, 0.0, pcbnew.F_Cu)
placements['C171'] = (make_cap('C171', '10uF', '0603'), 154.50, 72.50, 0.0, pcbnew.F_Cu)

j18 = pcbnew.FootprintLoad(lib_usb, 'USB3_A_Receptacle_Wuerth_692122030100')
j18.SetReference('J18'); j18.SetValue('USB3_A')
placements['J18'] = (j18, 158.00, 124.00, 0.0, pcbnew.F_Cu)

u50 = make_clone(ref_tsot, 'U50', 'AP22615A_TSOT26')
placements['U50'] = (u50, 150.00, 110.50, 0.0, pcbnew.F_Cu)

placements['C180'] = (make_cap('C180', '100nF', '0402'), 150.00, 107.50, 0.0, pcbnew.F_Cu)
placements['C181'] = (make_cap('C181', '100uF', '0805'), 147.00, 107.50, 0.0, pcbnew.F_Cu)
placements['R345'] = (make_res('R345', '10k', '0402'), 147.00, 105.50, 0.0, pcbnew.F_Cu)
placements['R346'] = (make_res('R346', '10k', '0402'), 147.00, 104.00, 0.0, pcbnew.F_Cu)
placements['R347'] = (make_res('R347', '10k', '0402'), 147.00, 102.50, 0.0, pcbnew.F_Cu)

placements['C182'] = (make_cap('C182', '100nF', '0402'), 153.00, 112.20, 0.0, pcbnew.F_Cu)
placements['D65']  = (make_clone(ref_tvs, 'D65', 'TPD1E0B04'), 155.00, 112.20, 0.0, pcbnew.F_Cu)
placements['C183'] = (make_cap('C183', '100nF', '0402'), 157.00, 112.20, 0.0, pcbnew.F_Cu)
placements['D66']  = (make_clone(ref_tvs, 'D66', 'TPD1E0B04'), 159.00, 112.20, 0.0, pcbnew.F_Cu)
placements['C184'] = (make_cap('C184', '100nF', '0402'), 161.00, 112.20, 0.0, pcbnew.F_Cu)
placements['D67']  = (make_clone(ref_tvs, 'D67', 'TPD1E0B04'), 163.00, 112.20, 0.0, pcbnew.F_Cu)
placements['D68']  = (make_clone(ref_tvs, 'D68', 'TPD1E0B04'), 165.00, 112.20, 0.0, pcbnew.F_Cu)

j16 = make_clone(ref_jst, 'J16', 'JST_SH_1x4_SM04B-SRSS-TB-LF-SN')
placements['J16'] = (j16, 155.00, 73.00, 0.0, pcbnew.B_Cu)

d64 = pcbnew.FootprintLoad(lib_sot, 'SOT-23')
d64.SetReference('D64'); d64.SetValue('PESD2CANFD24V-T')
placements['D64'] = (d64, 155.00, 79.50, 0.0, pcbnew.B_Cu)

u49 = pcbnew.FootprintLoad(lib_so, 'SOIC-8_3.9x4.9mm_P1.27mm')
u49.SetReference('U49'); u49.SetValue('TCAN1044V-Q1')
placements['U49'] = (u49, 155.00, 86.50, 0.0, pcbnew.B_Cu)

placements['R337'] = (make_res('R337', '60R4', '0402'), 161.00, 78.50, 0.0, pcbnew.B_Cu)
placements['R338'] = (make_res('R338', '60R4', '0402'), 161.00, 80.00, 0.0, pcbnew.B_Cu)
placements['C167'] = (make_cap('C167', '4n7', '0402'), 161.00, 81.50, 0.0, pcbnew.B_Cu)
placements['R340'] = (make_res('R340', '10k', '0402'), 161.00, 86.50, 0.0, pcbnew.B_Cu)
placements['C168'] = (make_cap('C168', '100nF', '0402'), 155.00, 91.50, 0.0, pcbnew.B_Cu)
placements['C169'] = (make_cap('C169', '100nF', '0402'), 155.00, 93.50, 0.0, pcbnew.B_Cu)

# Delete existing and place new
for ref in set(placements.keys()):
    old = board.FindFootprintByReference(ref)
    if old: board.Delete(old)

for ref, (fp, x, y, orient, layer) in placements.items():
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    fp.SetOrientationDegrees(orient)
    board.Add(fp)
    if fp.GetLayer() != layer:
        fp.Flip(fp.GetPosition(), False)

    # Bind pads
    if ref in comp_nets:
        pin_map = comp_nets[ref]
        for pad in fp.Pads():
            p_num = str(pad.GetNumber())
            if p_num in pin_map:
                net_item = netinfo.GetNetItem(pin_map[p_num])
                if net_item: pad.SetNet(net_item)
            elif 'SH' in p_num or 'MP' in p_num:
                gnd_net = netinfo.GetNetItem('GND')
                if gnd_net: pad.SetNet(gnd_net)

# 5. Extend internal solid ground planes
for z in board.Zones():
    if z.GetNetname() == 'GND':
        poly = z.Outline()
        if poly and poly.OutlineCount() > 0:
            bbox = poly.BBox()
            if pcbnew.ToMM(bbox.GetWidth()) > 100.0:
                outline = poly.Outline(0)
                for pt_idx in range(outline.PointCount()):
                    pt = outline.CPoint(pt_idx)
                    if pcbnew.ToMM(pt.x) > 150.0:
                        outline.SetPoint(pt_idx, pcbnew.VECTOR2I(pcbnew.FromMM(182.0), pt.y))

# 6. Add ground return vias
gnd_net = board.FindNet('GND')
def add_via(x_mm, y_mm, net=gnd_net):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
    via.SetWidth(pcbnew.FromMM(0.6))
    via.SetDrill(pcbnew.FromMM(0.3))
    via.SetNet(net)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    board.Add(via)

def add_track(p1, p2, net, layer=pcbnew.F_Cu, width=0.2):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(p1)
    t.SetEnd(p2)
    t.SetLayer(layer)
    t.SetWidth(pcbnew.FromMM(width))
    t.SetNet(net)
    board.Add(t)

# J17 ground return vias
j17_fp = board.FindFootprintByReference('J17')
for gnd_pin in ['6', '9', '14', '20', '25', '30', '34', '39']:
    p = j17_fp.FindPadByNumber(gnd_pin)
    if p:
        pos = p.GetPosition()
        vx = pcbnew.ToMM(pos.x) + (1.5 if pcbnew.ToMM(pos.x) > 173.0 else -1.5)
        add_via(vx, pcbnew.ToMM(pos.y))

# U51-U54 ground pin 11 return vias
for u_ref in ['U51', 'U52', 'U53', 'U54']:
    u = board.FindFootprintByReference(u_ref)
    p11 = u.FindPadByNumber('11')
    if p11:
        add_via(163.50, pcbnew.ToMM(p11.GetPosition().y))

# J18 USB ground vias
add_via(154.0, 116.5)
add_via(162.0, 116.5)
add_via(167.0, 120.5)

# CAN ground vias
add_via(155.0, 75.5)
add_via(155.0, 89.5)

# 7. Power routing
# +5V_EXP from F1 pin 2 to J17 pins 2, 4
f1_fp = board.FindFootprintByReference('F1')
f1_p2 = f1_fp.FindPadByNumber('2')
j17_p2 = j17_fp.FindPadByNumber('2')
j17_p4 = j17_fp.FindPadByNumber('4')
if f1_p2 and j17_p2 and j17_p4:
    exp_5v = f1_p2.GetNet()
    p_corner = pcbnew.VECTOR2I(j17_p2.GetPosition().x, f1_p2.GetPosition().y)
    add_track(f1_p2.GetPosition(), p_corner, exp_5v, width=0.5)
    add_track(p_corner, j17_p2.GetPosition(), exp_5v, width=0.5)
    add_track(j17_p2.GetPosition(), j17_p4.GetPosition(), exp_5v, width=0.5)

# +3V3_EXP from F2 pin 2 to J17 pin 1 and U51-U54 pin 19
f2_fp = board.FindFootprintByReference('F2')
f2_p2 = f2_fp.FindPadByNumber('2')
j17_p1 = j17_fp.FindPadByNumber('1')
if f2_p2 and j17_p1:
    exp_3v3 = f2_p2.GetNet()
    # F.Cu track from F2 pin 2 to J17 pin 1
    p_c1 = pcbnew.VECTOR2I(j17_p1.GetPosition().x, f2_p2.GetPosition().y)
    add_track(f2_p2.GetPosition(), p_c1, exp_3v3, width=0.5)
    add_track(p_c1, j17_p1.GetPosition(), exp_3v3, width=0.5)

    # Via bus on B.Cu to feed U51-U54 pin 19 without crossing right-side pads
    add_via(164.50, 74.725, exp_3v3)
    add_via(164.50, 84.725, exp_3v3)
    add_via(164.50, 94.725, exp_3v3)
    add_via(164.50, 104.725, exp_3v3)
    
    # B.Cu vertical bus
    add_track(pcbnew.VECTOR2I(pcbnew.FromMM(164.50), pcbnew.FromMM(74.725)),
              pcbnew.VECTOR2I(pcbnew.FromMM(164.50), pcbnew.FromMM(104.725)),
              exp_3v3, layer=pcbnew.B_Cu, width=0.4)
    # Connect to J17 pin 1 on F.Cu
    add_track(pcbnew.VECTOR2I(pcbnew.FromMM(164.50), pcbnew.FromMM(74.725)),
              j17_p1.GetPosition(), exp_3v3, layer=pcbnew.F_Cu, width=0.4)

    # Local stubs from vias into U51-U54 pin 19
    for uy in [74.725, 84.725, 94.725, 104.725]:
        add_track(pcbnew.VECTOR2I(pcbnew.FromMM(164.50), pcbnew.FromMM(uy)),
                  pcbnew.VECTOR2I(pcbnew.FromMM(162.863), pcbnew.FromMM(uy)),
                  exp_3v3, layer=pcbnew.F_Cu, width=0.3)

# USB_VBUS from U50 pin 1 to J18 pin 1
u50_fp = board.FindFootprintByReference('U50')
j18_fp = board.FindFootprintByReference('J18')
u50_p1 = u50_fp.FindPadByNumber('1')
j18_p1 = j18_fp.FindPadByNumber('1')
if u50_p1 and j18_p1:
    vbus_net = u50_p1.GetNet()
    p_mid = pcbnew.VECTOR2I(j18_p1.GetPosition().x, u50_p1.GetPosition().y)
    add_track(u50_p1.GetPosition(), p_mid, vbus_net, width=0.6)
    add_track(p_mid, j18_p1.GetPosition(), vbus_net, width=0.6)

# CAN differential pair on B.Cu
u49_fp = board.FindFootprintByReference('U49')
j16_fp = board.FindFootprintByReference('J16')
d64_fp = board.FindFootprintByReference('D64')
canh_u = u49_fp.FindPadByNumber('7')
canl_u = u49_fp.FindPadByNumber('6')
canh_j = j16_fp.FindPadByNumber('2')
canl_j = j16_fp.FindPadByNumber('3')
canh_d = d64_fp.FindPadByNumber('1')
canl_d = d64_fp.FindPadByNumber('2')
if canh_u and canh_j and canh_d:
    add_track(canh_u.GetPosition(), canh_d.GetPosition(), canh_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
    add_track(canh_d.GetPosition(), canh_j.GetPosition(), canh_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
if canl_u and canl_j and canl_d:
    add_track(canl_u.GetPosition(), canl_d.GetPosition(), canl_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)
    add_track(canl_d.GetPosition(), canl_j.GetPosition(), canl_u.GetNet(), layer=pcbnew.B_Cu, width=0.25)

# 8. Signal escape routing between U51-U54 and J17
print('Routing monotonic 3.3V GPIO traces...')
for u_ref in ['U51', 'U52', 'U53', 'U54']:
    u_fp = board.FindFootprintByReference(u_ref)
    u_map = comp_nets.get(u_ref, {})
    j_map = comp_nets.get('J17', {})
    for p_num, net_name in u_map.items():
        if not net_name.endswith('_3V3'): continue
        if net_name.startswith('/Peripherals/'): continue
        u_pad = u_fp.FindPadByNumber(p_num)
        j_pins = [jp for jp, jn in j_map.items() if jn == net_name]
        if not j_pins: continue
        j_pad = j17_fp.FindPadByNumber(j_pins[0])
        if not u_pad or not j_pad: continue
        
        up = u_pad.GetPosition()
        jp = j_pad.GetPosition()
        net_item = u_pad.GetNet()
        
        # If odd pin (X = 170.475): route on F.Cu
        if int(j_pins[0]) % 2 == 1:
            # 2-segment dogleg on F.Cu
            mid_x = pcbnew.FromMM(166.0)
            p_m1 = pcbnew.VECTOR2I(mid_x, up.y)
            p_m2 = pcbnew.VECTOR2I(mid_x, jp.y)
            add_track(up, p_m1, net_item, layer=pcbnew.F_Cu, width=0.2)
            add_track(p_m1, p_m2, net_item, layer=pcbnew.F_Cu, width=0.2)
            add_track(p_m2, jp, net_item, layer=pcbnew.F_Cu, width=0.2)
        else:
            # Even pin (X = 175.525): route via B.Cu under odd pads
            vx = pcbnew.FromMM(167.5)
            p_v1 = pcbnew.VECTOR2I(vx, up.y)
            add_track(up, p_v1, net_item, layer=pcbnew.F_Cu, width=0.2)
            add_via(167.5, pcbnew.ToMM(up.y), net_item)
            
            p_v2 = pcbnew.VECTOR2I(vx, jp.y)
            add_track(p_v1, p_v2, net_item, layer=pcbnew.B_Cu, width=0.2)
            add_via(173.0, pcbnew.ToMM(jp.y), net_item)
            add_track(p_v2, pcbnew.VECTOR2I(pcbnew.FromMM(173.0), jp.y), net_item, layer=pcbnew.B_Cu, width=0.2)
            add_track(pcbnew.VECTOR2I(pcbnew.FromMM(173.0), jp.y), jp, net_item, layer=pcbnew.F_Cu, width=0.2)

out_board = 'test_routed.kicad_pcb'
print(f'Saving test board: {out_board}')
board.Save(out_board)
print('Done!')
