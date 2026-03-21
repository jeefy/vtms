/*
 * Nextion 7" Display HMI Design Specification
 * ============================================
 * 
 * This file contains the complete design specification for creating
 * the Nextion display interface in the Nextion Editor.
 * 
 * Display: Nextion NX8048P070 (7" 800x480) or similar
 * 
 * To create the HMI file:
 * 1. Download Nextion Editor from https://nextion.tech/
 * 2. Create new project: 800x480 resolution
 * 3. Follow the component specifications below
 * 4. Compile and upload to your Nextion display
 */

// =============================================================================
// COLOR DEFINITIONS (RGB565 format for Nextion)
// =============================================================================
/*
 * Background:    0x0000 (Black)
 * White:         0xFFFF
 * Red:           0xF800
 * Green:         0x07E0
 * Blue:          0x001F
 * Yellow:        0xFFE0
 * Orange:        0xFD20
 * Dark Gray:     0x4208
 * Light Gray:    0xC618
 */

// =============================================================================
// PAGE 0: STARTUP PAGE (page name: "startup")
// =============================================================================
/*
 * Background: Black (0x0000)
 * 
 * Components:
 * 
 * 1. Logo/Title Text (t0)
 *    - objname: startup_title
 *    - x: 200, y: 150
 *    - w: 400, h: 60
 *    - txt: "VTMS GAUGE"
 *    - font: Large (font 2 or 3)
 *    - pco: White (0xFFFF)
 *    - bco: Black (0x0000)
 *    - xcen: 1 (center)
 *    - ycen: 1 (center)
 * 
 * 2. Status Text (t1)
 *    - objname: startup_txt
 *    - x: 200, y: 250
 *    - w: 400, h: 40
 *    - txt: "Initializing..."
 *    - font: Medium (font 1)
 *    - pco: Light Gray (0xC618)
 *    - bco: Black (0x0000)
 *    - xcen: 1 (center)
 *    - ycen: 1 (center)
 * 
 * 3. Version Text (t2)
 *    - objname: version_txt
 *    - x: 300, y: 400
 *    - w: 200, h: 30
 *    - txt: "v1.0.0"
 *    - font: Small (font 0)
 *    - pco: Dark Gray (0x4208)
 */

// =============================================================================
// PAGE 1: MAIN GAUGE PAGE (page name: "main")
// =============================================================================
/*
 * Background: Black (0x0000)
 * 
 * LAYOUT OVERVIEW (800x480):
 * ┌────────────────────────────────────────────────────────────────────────┐
 * │  [CAN]                                                                  │
 * │  ┌─────────────────────────┐    ┌─────────────────────────┐           │
 * │  │                         │    │                         │           │
 * │  │     TACHOMETER          │    │      SPEEDOMETER        │           │
 * │  │     [Progress Bar]      │    │      [Large Text]       │           │
 * │  │                         │    │                         │           │
 * │  │        4500 RPM         │    │        65 MPH           │           │
 * │  └─────────────────────────┘    └─────────────────────────┘           │
 * │                                                                        │
 * │  ┌───────────────┐    ┌───────────────┐                               │
 * │  │  WATER TEMP   │    │  OIL PRESS    │                               │
 * │  │  [Prog Bar]   │    │  [Prog Bar]   │                               │
 * │  │   195°F  ✓    │    │   55 PSI  ✓   │                               │
 * │  └───────────────┘    └───────────────┘                               │
 * │                                                                        │
 * │  ╔═══════════════════════════════════════════════════════════════╗    │
 * │  ║                    SHIFT! (overlay)                            ║    │
 * │  ╚═══════════════════════════════════════════════════════════════╝    │
 * └────────────────────────────────────────────────────────────────────────┘
 * 
 * COMPONENTS:
 * 
 * 1. CAN Status Indicator (p0)
 *    - objname: can_stat
 *    - Type: Picture or small rectangle
 *    - x: 10, y: 10
 *    - w: 20, h: 20
 *    - pco/bco: Green when connected, Red when disconnected
 * 
 * ---------- TACHOMETER SECTION ----------
 * 
 * 2. RPM Label (t0)
 *    - objname: rpm_label
 *    - x: 20, y: 30
 *    - w: 350, h: 30
 *    - txt: "RPM"
 *    - pco: White
 *    - font: Medium
 * 
 * 3. RPM Progress Bar (j0)
 *    - objname: rpm_gauge
 *    - Type: Progress Bar
 *    - x: 20, y: 70
 *    - w: 350, h: 80
 *    - val: 0
 *    - bco: Dark Gray (0x4208)
 *    - pco: Green (0x07E0) - will be changed dynamically
 * 
 * 4. RPM Value Text (t1)
 *    - objname: rpm_val
 *    - x: 20, y: 160
 *    - w: 350, h: 60
 *    - txt: "0"
 *    - pco: White
 *    - font: Extra Large (font 3 or 4)
 *    - xcen: 1
 * 
 * ---------- SPEEDOMETER SECTION ----------
 * 
 * 5. Speed Label (t2)
 *    - objname: speed_label
 *    - x: 430, y: 30
 *    - w: 350, h: 30
 *    - txt: "SPEED"
 *    - pco: White
 *    - font: Medium
 * 
 * 6. Speed Value (t3)
 *    - objname: speed_val
 *    - x: 430, y: 70
 *    - w: 280, h: 150
 *    - txt: "0"
 *    - pco: White
 *    - font: Huge (largest available, or use xfont)
 *    - xcen: 1
 *    - ycen: 1
 * 
 * 7. Speed Unit (t4)
 *    - objname: speed_unit
 *    - x: 710, y: 160
 *    - w: 70, h: 40
 *    - txt: "MPH"
 *    - pco: Light Gray
 *    - font: Medium
 * 
 * ---------- WATER TEMPERATURE SECTION ----------
 * 
 * 8. Temp Label (t5)
 *    - objname: temp_label
 *    - x: 20, y: 260
 *    - w: 180, h: 25
 *    - txt: "WATER TEMP"
 *    - pco: White
 *    - font: Small
 * 
 * 9. Temp Progress Bar (j1)
 *    - objname: temp_gauge
 *    - Type: Progress Bar
 *    - x: 20, y: 290
 *    - w: 180, h: 40
 *    - val: 50
 *    - bco: Dark Gray
 *    - pco: Green (dynamic)
 * 
 * 10. Temp Value (t6)
 *    - objname: temp_val
 *    - x: 20, y: 340
 *    - w: 120, h: 50
 *    - txt: "195"
 *    - pco: White
 *    - font: Large
 * 
 * 11. Temp Unit (t7)
 *    - objname: temp_unit
 *    - x: 145, y: 355
 *    - w: 55, h: 30
 *    - txt: "°F"
 *    - pco: Light Gray
 *    - font: Medium
 * 
 * ---------- OIL PRESSURE SECTION ----------
 * 
 * 12. Oil Label (t8)
 *    - objname: oil_label
 *    - x: 220, y: 260
 *    - w: 180, h: 25
 *    - txt: "OIL PRESS"
 *    - pco: White
 *    - font: Small
 * 
 * 13. Oil Progress Bar (j2)
 *    - objname: oil_gauge
 *    - Type: Progress Bar
 *    - x: 220, y: 290
 *    - w: 180, h: 40
 *    - val: 55
 *    - bco: Dark Gray
 *    - pco: Green (dynamic)
 * 
 * 14. Oil Value (t9)
 *    - objname: oil_val
 *    - x: 220, y: 340
 *    - w: 100, h: 50
 *    - txt: "55"
 *    - pco: White
 *    - font: Large
 * 
 * 15. Oil Unit (t10)
 *    - objname: oil_unit
 *    - x: 325, y: 355
 *    - w: 75, h: 30
 *    - txt: "PSI"
 *    - pco: Light Gray
 *    - font: Medium
 * 
 * ---------- SHIFT LIGHT OVERLAY ----------
 * 
 * 16. Shift Light Box (p1 or rectangle)
 *    - objname: shift_box
 *    - Type: Picture or filled rectangle
 *    - x: 150, y: 420
 *    - w: 500, h: 50
 *    - bco: Red (0xF800)
 *    - vis: 0 (hidden by default)
 * 
 * 17. Shift Text (t11) - placed on top of shift_box
 *    - objname: shift_txt
 *    - x: 150, y: 420
 *    - w: 500, h: 50
 *    - txt: "SHIFT!"
 *    - pco: White
 *    - bco: Red (0xF800)
 *    - font: Extra Large
 *    - xcen: 1
 *    - ycen: 1
 *    - vis: 0 (hidden by default)
 * 
 * ---------- ALERT OVERLAY ----------
 * 
 * 18. Alert Box (p2)
 *    - objname: alert_box
 *    - Type: Filled rectangle or picture
 *    - x: 200, y: 180
 *    - w: 400, h: 120
 *    - bco: Red (0xF800) - changes based on alert type
 *    - vis: 0 (hidden by default)
 * 
 * 19. Alert Text (t12)
 *    - objname: alert_txt
 *    - x: 200, y: 180
 *    - w: 400, h: 120
 *    - txt: "ALERT"
 *    - pco: White
 *    - bco: Red (0xF800)
 *    - font: Huge
 *    - xcen: 1
 *    - ycen: 1
 *    - vis: 0 (hidden by default)
 */

// =============================================================================
// FONTS REQUIRED
// =============================================================================
/*
 * You'll need to create or import the following fonts in Nextion Editor:
 * 
 * Font 0: Small (height ~16-20px)
 *         - Used for: labels, units
 * 
 * Font 1: Medium (height ~24-30px)
 *         - Used for: secondary values
 * 
 * Font 2: Large (height ~40-50px)
 *         - Used for: gauge values
 * 
 * Font 3: Extra Large (height ~60-80px)
 *         - Used for: RPM value, alerts
 * 
 * Font 4: Huge (height ~100-120px)
 *         - Used for: Speed value (main focus)
 * 
 * Recommended: Use a bold, sans-serif font like "Arial Bold" or "Segment7"
 * for the gauge numbers for better readability.
 */

// =============================================================================
// NEXTION EDITOR SETUP STEPS
// =============================================================================
/*
 * 1. Open Nextion Editor
 * 2. File -> New -> Select your display model (NX8048P070-011C for 7" Enhanced)
 * 3. Set orientation: Horizontal (800x480)
 * 
 * 4. Create Page 0 (startup):
 *    - Right-click page list -> Add Page
 *    - Rename to "startup"
 *    - Set background to black
 *    - Add text components as specified above
 * 
 * 5. Create Page 1 (main):
 *    - Add new page, rename to "main"
 *    - Set background to black
 *    - Add all components as specified above
 *    - Set vis=0 for shift_box, shift_txt, alert_box, alert_txt
 * 
 * 6. Import/Create Fonts:
 *    - Tools -> Font Generator
 *    - Create fonts at various sizes
 *    - Add to project
 * 
 * 7. Compile and Upload:
 *    - Compile -> Compile
 *    - Upload to display via USB/Serial
 * 
 * 8. Test with ESP32:
 *    - Connect Nextion TX to ESP32 GPIO16 (RX)
 *    - Connect Nextion RX to ESP32 GPIO17 (TX)
 *    - Connect GND to GND
 *    - Power Nextion with 5V
 */

// =============================================================================
// ALTERNATIVE: USING DRAW COMMANDS (if you want arc gauges)
// =============================================================================
/*
 * The Nextion Enhanced series supports drawing commands for custom gauges.
 * You can create circular/arc gauges using these commands from the ESP32:
 * 
 * // Draw arc gauge
 * cirs x,y,r,color           // Draw filled circle
 * line x1,y1,x2,y2,color     // Draw line (for needle)
 * arc x,y,r,w,start,end,color // Draw arc
 * 
 * Example for circular tachometer:
 * - Draw background arc (dark gray)
 * - Draw filled arc from 0 to current RPM (colored by zone)
 * - Draw tick marks
 * - Draw center circle
 * - Draw needle line
 * 
 * This requires more ESP32 processing but creates nicer gauges.
 */

// =============================================================================
// NEXTION COMMAND REFERENCE (for ESP32 code)
// =============================================================================
/*
 * All commands must end with three 0xFF bytes.
 * 
 * Change page:
 *   page main\xFF\xFF\xFF
 * 
 * Set text:
 *   rpm_val.txt="4500"\xFF\xFF\xFF
 * 
 * Set number:
 *   rpm_gauge.val=56\xFF\xFF\xFF
 * 
 * Set color:
 *   rpm_gauge.pco=63488\xFF\xFF\xFF   // 63488 = 0xF800 (red)
 * 
 * Set visibility:
 *   vis shift_box,1\xFF\xFF\xFF       // Show
 *   vis shift_box,0\xFF\xFF\xFF       // Hide
 * 
 * Set background color:
 *   alert_box.bco=65504\xFF\xFF\xFF   // 65504 = 0xFFE0 (yellow)
 */
