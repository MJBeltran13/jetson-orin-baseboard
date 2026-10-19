# Jetson Orin Baseboard PCB Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use checkboxes to record evidence. Do not mark the board fabrication-ready while a release gate remains open.

**Goal:** Repair the current carrier board so its schematic, BOM, PCB connectivity, and manufacturing files agree, then validate operation on hardware.

**Architecture:** Correct the schematic source first, update the current PCB through KiCad, then repair placement and routing. Preserve the original carrier functions and existing verified routing wherever possible. Treat mechanical fit, electrical correctness, and bench qualification as separate gates.

**Tech Stack:** KiCad 10.0.7, `kicad-cli`, KiCad Python API `pcbnew` for structural PCB operations, and Python standard-library XML checks. The current PCB uses KiCad 10 format; do not down-convert it to KiCad 9.

**Spec:** The repair specification and release gates in this document. Follow `AGENTS.md` and `doc/PROMPT_STANDARDS.md` for net tracing, file safety, and verification.

## Repair specification

Baseline checked on 2026-10-14 against the saved working tree:

| Check | Baseline |
| --- | --- |
| PCB SHA-256 | `f084611805ada34c5b8c71082d24961fa3ef0886c39c14735ea3090708ef6036` |
| Copper shorts reported | 0 |
| Other DRC errors | 29 |
| Unconnected items | 187 |
| Schematic/PCB parity warnings | 82 |
| ERC pin conflicts with the check enabled | 7 |

The seven ERC errors require investigation; several arise from incorrect symbol pin types or intentional power ORing. They are not seven proven electrical shorts. Library and silkscreen warnings must also be distinguished from electrical defects.

### Scope decisions

- **USB1 ownership — confirmed:** The user selected M.2 Bluetooth; USB-A is disabled. Keep R20/R52 populated to connect USB1 to M.2 J1. Remove J18's active branch, its dedicated power switch, coupling/decoupling capacitors, and ESD circuit from the schematic/BOM/PCB. Preserve M.2 PCIe Wi-Fi and the existing USB-C ports. No USB hub or alternate assembly variant is required.
- **Mechanical envelope — confirmed:** The user allows mechanical changes. The expansion outline and connector/component positions may change to achieve safe placement and routing. Maintain compatible SoM seating, mounting, and required clearances. Record the final dimensions and changed mounting/connector positions in the mechanical outputs; the current malformed arcs are not a dimensional reference.

Both scope decisions are confirmed. Implementation must still resolve physical fit and pass the release gates below.

## Global constraints

- Start from the latest saved working tree, including uncommitted changes. Never replace it wholesale with `/tmp/jetson-board-fix`: that copy predates the latest PCB edits.
- Check KiCad locks and open editors before replacing design files. Save and close affected editors, or work in a separate repair copy.
- Back up the starting files and record hashes. Recheck them before integration to catch concurrent edits.
- Use structural edits and KiCad APIs. Preserve component and pin UUIDs; avoid broad formatting rewrites and regex-based netlist mutation.
- Trace every changed net as sheet, reference, and pin number/name. Preserve unrelated connections and module mounting geometry.
- Do not route with the current script's unchecked right-angle segments. Repair or disable that routing path before it can regenerate shorts.
- Verify each signal's actual voltage domain. CAN and I2C1 are 3.3V exceptions to the predominantly 1.8V SoM interfaces.
- Derive impedance, coupling, and timing requirements from the NVIDIA guide, component data, and approved fabricator stackup. Do not apply blanket 100Ω or 100nF substitutions to existing high-speed interfaces.
- Do not clear DRC by broadly weakening rules or suppressing checks. Document any justified, narrowly scoped exception with manufacturer/fabricator evidence.

## Review focus

1. **Concurrent KiCad saves:** Integration must not overwrite newer user edits; Task 1 checks input hashes.
2. **USB1 ownership:** Only M.2 Bluetooth receives USB1; Tasks 2 and 6 verify populated R20/R52 and the absence of the J18 branch.
3. **Unpowered module or expansion rail:** No peripheral may back-power SoM I/O; Tasks 2 and 7 check voltage domains and power transitions.
4. **Larger power parts:** Inductors and gate clamps must clear copper, the PoE module, SoM, and standoffs; Tasks 3 and 5 enforce physical fit.
5. **SuperSpeed routing:** A visually tidy route can still have stubs or reference-plane discontinuities; Tasks 5 and 7 check the complete channel.

## Task 1 — Establish the repair baseline and runnable checks

**Files:** All current `.kicad_sch` files, PCB, project settings, custom rules, and library tables. Create `scripts/check_board.py` only for reusable electrical assertions and report checks.

**Consumes:** Current saved design and decisions above. **Produces:** A protected baseline, fresh XML netlist, DRC/ERC reports, and a failing electrical regression check.

- [ ] Snapshot the complete saved project and local changes without deleting or resetting user files.
- [ ] Check locks/editor state, record hashes, and identify the intended mechanical envelope.
- [ ] Re-export the current netlist and rerun DRC with schematic parity, all track errors, and zone refill in memory.
- [ ] Enable pin-conflict ERC in a temporary copy to reproduce the seven current errors.
- [ ] Write one standard-library check with interface `check_board.py <reports-directory>`. Read `netlist.xml`, `erc.json`, and `drc.json`; report all failures and exit nonzero on a failed gate. Check populated R20/R52, USB1 connectivity from J15 pins 115/117 through R52/R20 to M.2 J1 pins 5/3, absence of J18/U50 and their dedicated branch, J15 pins 191/189 on J17 pins 3/5 without the 1.8V translator channels, unique references, and required report gates. KiCad XML expresses DNP as a property element, not a component attribute.
- [ ] Run it against the baseline and confirm it fails for the known faults. Keep reports outside the source tree; record commands and input hashes in the repair evidence.

**Gate:** Baseline reproduced, user changes protected, and the check demonstrably detects the faults it will later prove repaired.

## Task 2 — Correct schematic connectivity, pin models, and assembly intent

**Files:** `expansion.kicad_sch`, `can.kicad_sch`, `m-2.kicad_sch`, `peripherals.kicad_sch`, `som.kicad_sch`, affected cached symbols in `csi.kicad_sch`, `usb.kicad_sch`, `usb3.kicad_sch`, `ethernet.kicad_sch`, `supply.kicad_sch`, and project/library settings.

**Consumes:** Baseline netlist and confirmed M.2 Bluetooth ownership. **Produces:** A verified schematic netlist and a complete list of intentional additions, deletions, pin changes, and BOM changes.

- [ ] Remove the disabled USB-A circuit: J18, U50, C180–C184, D65–D68, and R345–R347, after confirming each remains dedicated to that branch in the latest files. Remove their wiring, labels, footprints, and obsolete copper. This retires the faulty U50 input and R347 setting; do not redesign an unused USB-A supply.
- [ ] Keep R20/R52 populated and included in the BOM. Verify M.2 supply, Bluetooth reset/disable/wake signal domains, USB enumeration, and required module firmware. Preserve F1/F2 and the 40-pin header's separate power circuit.
- [ ] Route SoM J15 pins 191/I2C1_SDA and 189/I2C1_SCL to J17 pins 3/5 in the correct 3.3V domain. Do not raise all of U51's VCCA: its other channels serve 1.8V signals. Bypass the two channels or isolate them into correctly powered circuitry; mark unused translator pins NC.
- [ ] Retire J11 and components/wires serving only that connector, after checking every remaining consumer. Preserve shared camera control, fan, I2C, and other peripheral circuitry.
- [ ] Remove obsolete C111/C113 SuperSpeed branches after retiring J11 and J18. Mark now-unused USBSS1 SoM pins 39/41/45/47 NC at the pins. Disable the unused SuperSpeed port in the BSP while retaining the USB2 host port serving Bluetooth; preserve other USB interfaces.
- [ ] Correct datasheet-proven open-drain and passive power-path pin types. Resolve all seven ERC findings individually; keep `pin_to_pin` checking enabled.
- [ ] Reconcile every retained ordered part with symbol, footprint, and BOM. Pay particular attention to J17 SMD versus through-hole, CAN parts, and F2's differing fuse value. Remove USB-A from product documentation and fabrication BOMs.
- [ ] Recover/configure project libraries without replacing exact cached parts with different modern variants. Document any remaining exact-cache mismatch warnings.
- [ ] Document CAN termination: fit R337/R338 at an endpoint; DNP both for an intermediate node. Keep U49 VIO at the verified 3.3V domain.
- [ ] Export the revised XML and run the regression check. Compare all retained, unrelated component pin/net assignments against baseline.

**Gate:** Zero unexplained ERC errors; intended electrical assertions pass; unrelated connections are preserved; no unexplained component/BOM/package discrepancy remains.

## Task 3 — Resolve power protection with a physical-fit gate

**Files:** `supply.kicad_sch`, PCB, and any necessary verified project footprint.

**Consumes:** Verified power topology, actual rail load budgets, and mechanical envelope. **Produces:** An electrically and mechanically justified power repair, with calculations and bench criteria.

- [ ] Recheck Q15/Q16 gate-source voltage across startup, loading, and input-source changes. Q15's SSM3J332R ±12V gate rating requires protection assessment for the documented 15–20V input.
- [ ] Evaluate 8.2V gate-source clamps, such as BZT52H-B8V2,115, with cathode at source and anode at gate. Check clamp current, startup, reverse blocking, and placement before adding D69/D70.
- [ ] Recalculate R173/R239 OCP against full-load valley current, ripple, tolerances, inductance versus bias/temperature, and regulator fault response. Candidate 100kΩ selects approximately 17.3A valley OCP; it does not by itself prove the original inductors survive faults.
- [ ] Check candidate inductors against copper and mechanical drawings before changing the BOM. Earlier candidates were XAL7030-601MEC for L1 and SRP7030CA-1R0M for L4. Placement trials found collisions with existing routing and the PoE/module envelope; these are not drop-in replacements.
- [ ] If qualified parts cannot fit, resolve a power-stage relocation or explicit rail-capacity change before proceeding. Do not silently derate the board or place parts beneath an unverified module clearance.
- [ ] Preserve short switching loops, feedback routing, ground returns, and output-current copper capacity. Recheck compensation and thermal losses for any inductance/DCR change.

**Gate:** Power modification has a calculated operating range, demonstrated physical fit, no DRC collision, and explicit startup/fault/thermal bench tests. Leave this gate open if placement or fault survival remains unresolved.

## Task 4 — Repair manufacturing geometry and synchronize the PCB

**Files:** `jetson-orin-baseboard.kicad_pcb`, library tables/footprints, and justified custom rules.

**Consumes:** Approved schematic netlist and mechanical envelope. **Produces:** A synchronized, manufacturable placement with a valid outline.

- [ ] Update the current PCB from the repaired schematic using KiCad; preserve positions and verified original routing unless a specific conflict requires change.
- [ ] Remove retired footprints and dedicated copper. Preserve shared upstream nets; identify and remove obsolete stubs separately.
- [ ] Apply DNP state, real package sizes, symbol association paths, and BOM fields consistently.
- [ ] Disconnect PCB ground stubs from unused PG pins only if Task 2 changes them to NC; preserve other ground connections.
- [ ] Replace malformed Edge.Cuts arcs/segments with one closed, non-self-intersecting outline. Preserve intended dimensions and approved mounting geometry.
- [ ] Fix F1's zero board-edge copper clearance; check component and connector clearance at the repaired edge.
- [ ] Resolve J3 NPTH/J12 mounting-pad copper interference from manufacturer drawings. Correct footprints or approved placement; do not waive actual zero clearance.
- [ ] Resolve duplicate ground-zone priorities without changing intended net connectivity.
- [ ] Review courtyards and 3D mechanical fit, including PoE module, SoM standoffs, remaining USB-C shells, header, and power parts. Distinguish duplicate artwork from actual assembly collisions.

**Gate:** Valid board outline, verified packages, zero unexplained parity warnings, and zero unapproved mechanical/edge/hole interference.

## Task 5 — Complete routing with power and high-speed constraints

**Files:** PCB and verified netclass/custom-rule settings.

**Consumes:** Synchronized placement. **Produces:** Fully connected PCB with reviewed current paths, differential channels, and return planes.

- [ ] Start from the 187 missing connections and generate a pin-level routing checklist. Recount after synchronization; do not treat 187 as a fixed target.
- [ ] Route power and ground first. Size traces, pours, thermal connections, and via arrays for worst-case current and temperature, including header fuses and the retained USB-C ports.
- [ ] Extend continuous reference planes into the expansion area; refill zones and check for isolated copper and unconnected grounds.
- [ ] Route CAN, translator supplies/enables, header signals, and remaining low-speed connections with clearance-aware routing.
- [ ] Preserve or repair the M.2 Bluetooth USB1 D+/D− channel. Verify polarity, widths/gaps, pair skew, return continuity, and vias against the approved stackup/design guide. Confirm the disabled USB-A branch leaves no stub. Preserve other existing USB SuperSpeed channels.
- [ ] Remove obsolete connector branches and high-speed stubs. Do not let a generic autorouter independently route differential members or alter verified original high-speed routes without review.
- [ ] Refill zones and run full DRC after each routing group. Inspect both copper and assembly placement visually.

**Gate:** Zero unconnected items, zero copper shorts, and zero unexplained electrical/manufacturing DRC errors. High-speed and high-current constraints have separate review evidence.

## Task 6 — Run release checks and inspect fabrication outputs

**Files:** Verification script, project documentation, BOM, and generated manufacturing outputs.

**Consumes:** Routed board and verified schematic. **Produces:** A fabrication-review package tied to exact design hashes.

- [ ] Run fresh full ERC with pin-conflict checking enabled, the electrical regression check, and DRC with parity, zone refill, and all track errors.
- [ ] Require zero unconnected items and zero unexplained errors. Review every remaining warning/exclusion with a recorded reason; do not claim a clean board from suppressed checks.
- [ ] Validate the selected M.2 Bluetooth configuration: R20/R52 populated, J18 branch absent, other USB-C ports retained, and BSP port assignment correct.
- [ ] Export Gerbers, drill files, placement files, BOM, schematic PDF, and 3D assembly. Inspect the actual outputs for outline closure, drill/pad interaction, correct copper layers, polarity, orientation, and package agreement.
- [ ] Obtain an independent electrical/layout review and fabricator confirmation of stackup, impedance, and manufacturing limits.
- [ ] Recheck input hashes before integrating the repair into the user's active project. Reconcile any newer changes instead of overwriting them.

**Gate:** Fabrication-review package passes all documented design checks. Label it **bench qualification pending** until Task 7 passes.

## Task 7 — Qualify assembled hardware

**Consumes:** Assembled board, intended SoM/BSP, supported power sources, and interface fixtures. **Produces:** Measured operating limits and evidence of working interfaces.

- [ ] Check resistance/continuity and polarity with the SoM absent; then power from a current-limited supply and verify all rails.
- [ ] Measure startup/shutdown sequencing, rail discharge, gate-clamp behavior, and absence of back-power with the module or expansion rails off.
- [ ] Test each supported DC, USB-PD, and PoE source and source transitions under load. Validate regulator stability and controlled overload response.
- [ ] Load SoM, NVMe, USB, and permitted header power together; record hot-component temperatures and rail droop.
- [ ] Test recovery/debug UART, retained USB-C USB2/USB3 enumeration and sustained transfer, M.2 Wi-Fi and Bluetooth, CAN-FD with correct termination, header interfaces, cameras, HDMI, and Ethernet.
- [ ] Exercise reset, recovery, suspend/resume, and cold/hot starts. Check HDMI sleep pull-down requirements if SC7 is supported.

**Gate:** Only call the board operational within the tested module, firmware, power, load, and environmental limits. Passing DRC/ERC alone does not satisfy this gate.

## Verification commands

Run from the repaired project directory. Resolve `kicad-cli` to the installed executable; on this host it is `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`.

```sh
kicad_cli="/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
mkdir -p /tmp/jetson-pcb-repair-checks
"$kicad_cli" sch export netlist --format kicadxml \
  -o /tmp/jetson-pcb-repair-checks/netlist.xml jetson-orin-baseboard.kicad_sch
"$kicad_cli" sch erc --format json --severity-all \
  -o /tmp/jetson-pcb-repair-checks/erc.json jetson-orin-baseboard.kicad_sch
"$kicad_cli" pcb drc --schematic-parity --refill-zones --all-track-errors \
  --format json --severity-all \
  -o /tmp/jetson-pcb-repair-checks/drc.json jetson-orin-baseboard.kicad_pcb
python3 scripts/check_board.py /tmp/jetson-pcb-repair-checks
```

The check script must inspect report contents and enabled/ignored checks. KiCad exit code 0 alone is not proof: report-generating commands can succeed while reporting violations. Do not use `--save-board` during verification of an open project.

The regression check implements the confirmed M.2 Bluetooth configuration; USB-A is not part of the repaired board's active interfaces.

## Primary references

- [NVIDIA Orin NX/Nano Product Design Guide](https://developer.nvidia.com/downloads/jetson-orin-nx-series-nano-series-design-guide): pin domains, power sequencing, channel constraints, and sleep behavior.
- [Diodes AP22615](https://www.diodes.com/datasheet/download/AP22815_615.pdf): pinout, input/output capacitors, and current-limit setting.
- [TI TXS0108E](https://www.ti.com/lit/ds/symlink/txs0108e.pdf): translator operating conditions and load limits.
- [Toshiba SSM3J332R](https://toshiba.semicon-storage.com/info/docget.jsp?did=2620): gate-source rating and package data.
- [Vishay SiC431](https://www.vishay.com/docs/74589/sic431.pdf): OCP selection, ripple, compensation, and fault response.
- [Coilcraft XAL7030](https://www.coilcraft.com/getmedia/0d05a05e-d55d-4a0c-911d-46bd73686633/xal7030.pdf) and [Bourns SRP7030CA](https://www.bourns.com/docs/product-datasheets/srp7030ca.pdf): candidate electrical ratings and mechanical drawings.

## Execution order and stop conditions

Execute Tasks 1–2 before routing. Resolve the power-fit decision in Task 3 before final placement, then complete Tasks 4–6. Task 7 follows assembly. Stop dependent work when mechanical fit or a release gate is unresolved; continue independent checks. Record any deferred item explicitly rather than marking its task complete.

This plan permits mechanical changes needed for the repair. A simultaneous-USB hub redesign or rail derating still requires an explicit scope decision. Verify any supplied enclosure constraints before finalizing the mechanical outputs.
