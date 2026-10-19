# Zero-Error Prompting Standards & Recipes

This guide provides standards, formulas, and battle-tested prompt templates to ensure 100% accurate, hallucination-free assistance when working on the **Antmicro Jetson Orin Baseboard** KiCad 9.x project.

---

## 1. The 4-Part "Zero-Error" Prompt Formula

To get completely reliable, verifiable results from AI assistants without ambiguities or guesses, structure prompts using this 4-part formula:

$$\mathbf{[Action]} + \mathbf{[Target\ Sheet/File]} + \mathbf{[Reference\ Standard]} + \mathbf{[Verification\ Output]}$$

| Element | Description | Example |
| :--- | :--- | :--- |
| **1. Action** | The exact engineering task to perform | `Trace`, `Audit`, `Calculate`, `Modify`, `Script` |
| **2. Target** | Specific schematic sheet(s) or PCB files | `som.kicad_sch`, `supply.kicad_sch`, `jetson-orin-baseboard.kicad_pcb` |
| **3. Standard** | Ground truth specification or design guide | NVIDIA Orin NX/Nano Design Guide, KiCad 9 DRC, Component Datasheet |
| **4. Verification** | Concrete evidence required in the output | Pin-to-pin mapping table, voltage level check, S-expression diff |

---

## 2. Copy-Pasteable Prompt Templates

### Category A: Hardware & Schematic Reviews

#### Template A1: Deep Net & Pinout Trace
```text
Trace net [NET_OR_BUS_NAME] starting from [SOURCE_SHEET, e.g. som.kicad_sch] through to [DESTINATION_SHEET, e.g. m-2.kicad_sch / csi.kicad_sch].
1. List all intermediate components (resistors, level shifters, capacitors).
2. Check signal voltage level against NVIDIA Orin NX/Nano Pinmux (1.8V vs 3.3V).
3. Present the result in a step-by-step table: (Sheet -> Component Ref -> Pin -> Net Name).
```

#### Template A2: Differential Pair Polarity & AC Coupling Audit
```text
Inspect the differential pairs for [INTERFACE, e.g. PCIe / MIPI CSI-2 / USB 3.2] in [SHEET_NAME].
1. Verify polarity pairing (_P / _N or + / -) from transmitter to receiver.
2. Confirm presence and value of AC coupling capacitors if required by standard (e.g., 100 nF on PCIe TX).
3. Flag any inversions or uncoupled lines.
```

#### Template A3: Power Domain & Regulator Budget Check
```text
Review the power supply architecture in supply.kicad_sch:
1. List each regulator, its input rail, output rail, nominal voltage, and maximum rated current.
2. Verify that downstream loads (SoM VDD_IN, M.2 3.3V rail, USB 5V VBUS) do not exceed regulator limits.
3. Check that Power Good (PG) signals and enable pins properly gate downstream power states.
```

---

### Category B: BOM & Component Auditing

#### Template B1: I2C Bus & Device Address Audit
```text
Scan all schematic sheets for I2C peripherals.
Generate a table containing:
- Bus Name (e.g. I2C0, I2C1, CAM_I2C)
- Pull-up resistor values and their pull-up voltage rail (+1V8 vs +3V3)
- Connected ICs with Reference Designator, Manufacturer Part Number (MPN)
- 7-bit Hex Slave Address
Flag any address collisions on the same bus.
```

#### Template B2: ESD & Connector Protection Audit
```text
Inspect [CONNECTOR_SHEET, e.g. usb.kicad_sch / hdmi.kicad_sch / ethernet.kicad_sch].
1. Identify all user-accessible external pins on [CONNECTOR_REF, e.g. J1].
2. Verify if TVS diode arrays or ESD suppression devices are placed on data lines and power pins.
3. List any unprotected signal lines.
```

---

### Category C: KiCad Design & Schematic Modifications

#### Template C1: Adding Components / Test Points
```text
First, verify that no KiCad lock files (~*.lck) are present in the directory.
Then, propose an edit to [SHEET_NAME] to add [COMPONENT_TYPE, e.g. 0402 test point / pull-up resistor] to net [NET_NAME].
Requirements:
1. Keep S-expression syntax valid and balanced.
2. Assign next available reference designator.
3. Show the exact unified diff and list affected pin coordinates.
```

#### Template C2: Renaming Nets / Global Labels Across Sheets
```text
We need to rename net [OLD_NET_NAME] to [NEW_NET_NAME] across the project.
1. Search all .kicad_sch files for occurrences of this net name or global label.
2. List all sheets and pin instances where it appears.
3. Propose exact replacement diffs while maintaining S-expression formatting.
```

---

### Category D: KiCad Python Automation & Layout Analysis

#### Template D1: Differential Pair Impedance Audit Script
```text
Write a standalone Python script using KiCad 9's pcbnew module to inspect jetson-orin-baseboard.kicad_pcb.
The script should:
1. Iterate over all differential pairs defined in net classes.
2. Measure track width, pair spacing, and calculate nominal differential impedance against the board stackup.
3. Print a summary table flagging any pairs deviating from [TARGET_OHMS, e.g. 90/100] +/- 10%.
```

#### Template D2: BOM Extraction Script
```text
Create a Python script to parse all .kicad_sch files in this repository.
Extract: Reference, Value, Footprint, Datasheet, and Sheet Name.
Sort by Reference Designator and output to a clean CSV file.
```

---

## 3. Anti-Patterns & Common Pitfalls

| Anti-Pattern | Why It Causes Errors | Correct Approach |
| :--- | :--- | :--- |
| *"Check my schematic."* | Vague; model will skim or guess which sheet. | Specify the exact sheet name (e.g., `som.kicad_sch`) and target nets. |
| *"Modify J2 connector pinout."* | Risks breaking KiCad S-expression syntax or clashing with an open KiCad session. | Request a lock file check first, then ask for a verified S-expression diff. |
| *"Is 3.3V connected to the SoM?"* | May miss level shifters or pull-ups. | Ask to trace through intermediate resistors and check level shifters. |
| *"Assume standard Jetson pinout."* | Orin NX/Nano pinouts differ from Xavier NX and TX2. | Explicitly cite the **NVIDIA Jetson Orin NX and Orin Nano Product Design Guide**. |

---

## 4. Quick Pre-Prompt Checklist

Before submitting a request, verify:
- [ ] Have I specified the target sheet (`som`, `supply`, `csi`, `ethernet`, `hdmi`, `usb`, `m-2`, `peripherals`)?
- [ ] Have I stated the standard or reference criteria (e.g. 1.8V logic, 100 $\Omega$ diff pair, Orin Design Guide)?
- [ ] Is KiCad saved and closed if requesting file edits (to avoid `.lck` conflicts)?
- [ ] Did I ask for tabular / diff output for easy review?
