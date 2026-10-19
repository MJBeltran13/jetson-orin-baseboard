# Agent Guidelines for Jetson Orin Baseboard

This repository contains the open-hardware design files for the **Quadro Jetson Orin Baseboard** supporting NVIDIA Jetson Orin NX and Jetson Orin Nano System on Modules (SoMs), designed in **KiCad 9.x**.

All AI assistants and automated tools operating in this repository must strictly adhere to the guidelines and verification standards below to prevent design errors, net misconnections, and file corruptions.

---

## 1. Project Architecture & File Map

- **Root Schematic**: [`jetson-orin-baseboard.kicad_sch`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/jetson-orin-baseboard.kicad_sch)
- **Sub-Sheets (Hierarchical)**:
  - [`som.kicad_sch`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/som.kicad_sch): 260-pin SO-DIMM connector for Jetson Orin NX/Nano SoM
  - [`supply.kicad_sch`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/supply.kicad_sch): Power inputs, DC/DC buck converters, LDOs, USB-PD controllers
  - [`csi.kicad_sch`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/csi.kicad_sch): MIPI CSI-2 camera interfaces (50-pin unified connectors)
  - [`ethernet.kicad_sch`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/ethernet.kicad_sch): Gigabit Ethernet PHY, PoE circuit, RJ45 with magnetics
  - [`hdmi.kicad_sch`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/hdmi.kicad_sch): Micro HDMI interface, level shifting, ESD protection
  - [`usb.kicad_sch`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/usb.kicad_sch) & [`usb3.kicad_sch`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/usb3.kicad_sch): USB-C 10Gbps ports, muxes, PD logic, UART debug
  - [`m-2.kicad_sch`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/m-2.kicad_sch): M.2 Key M (PCIe x4 NVMe) and M.2 Key E (Wi-Fi/BT)
  - [`peripherals.kicad_sch`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/peripherals.kicad_sch): Expansion connectors, RTC battery, I2C/SPI/UART headers
- **PCB Layout**: [`jetson-orin-baseboard.kicad_pcb`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/jetson-orin-baseboard.kicad_pcb)
- **Documentation**: [`doc/`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/doc) (Sphinx source files in `doc/source/`)

---

## 2. Hardware & Schematic Verification Rules (Zero-Hallucination Policy)

1. **Explicit Cross-Sheet Tracing**:
   - Never assume net names or pin destinations.
   - Trace hierarchical sheet pins and `global_label` tags across sheets (e.g., verifying a signal on `som.kicad_sch` corresponds to the exact sheet pin in `jetson-orin-baseboard.kicad_sch` and its destination sheet).
   - When citing connections, specify: **Sheet Name $\rightarrow$ Component Designator $\rightarrow$ Pin Number/Name**.

2. **Voltage Domain & Logic Level Checks**:
   - Jetson Orin NX/Nano SoM GPIOs, I2C, and SPI operate predominantly at **1.8V**.
   - Always check for bidirectional level shifters (or pull-up voltage rails) when connecting SoM lines to 3.3V or 5V peripherals.
   - Flag any direct connection between 1.8V pins and >1.8V voltage rails as a critical electrical hazard.

3. **High-Speed & Differential Pair Integrity**:
   - Verify differential pairs for:
     - Correct polarities (`_P` / `_N` or `+` / `-`).
     - AC coupling capacitor requirements (e.g., PCIe TX pairs require 100 nF capacitors).
     - Target differential impedance constraints:
       - USB 2.0: 90 $\Omega$
       - USB 3.x / PCIe / MIPI CSI-2 / HDMI / GbE: 100 $\Omega$

4. **Power Sequencing & Thermal Capacity**:
   - Audit power nets (`+V_IN`, `+5V`, `+3V3`, `+1V8`, `VDD_IN`).
   - Check current ratings on inductors, power FETs, and polyfuses against worst-case SoM consumption (up to 25W for Orin NX).
   - Ensure power-good (`PG`) signals properly gate downstream regulators and reset lines (`SYS_RESET_N`, `POWER_EN`).

---

## 3. KiCad File Safety & Modification Protocol

1. **Lock File Awareness**:
   - Check for active lock files (`~*.lck`, e.g., `~jetson-orin-baseboard.kicad_sch.lck`) before modifying schematic or PCB files.
   - If lock files exist, inform the user that KiCad is open in the GUI to prevent accidental file overwrite conflicts.

2. **S-Expression Format Integrity**:
   - KiCad 9.x files use S-expressions (`(kicad_sch ...)`, `(kicad_pcb ...)`).
   - Never perform blind string replacements that could unbalance parentheses or corrupt unique UUIDs (`uuid`).
   - For automated PCB edits or audits, prefer python scripts utilizing the KiCad Python API (`pcbnew`).

3. **Diff & Verification Gate**:
   - Every file change must produce a minimal, readable diff.
   - Clearly report any new components, modified net labels, or pin alterations.
   - Ensure no dangling or unintended floating nets are introduced.

---

## 4. Prompt Handling Standards

When the user asks for design analysis, reviews, or changes:
- Verify findings against physical schematic files rather than general memory.
- Cite specific component reference designators (e.g., `U1`, `J5`, `R12`, `Q3`).
- For prompt templates and structured queries, consult [`doc/PROMPT_STANDARDS.md`](file:///Users/steerhub4/Documents/GitHub/jetson-orin-baseboard/doc/PROMPT_STANDARDS.md).
