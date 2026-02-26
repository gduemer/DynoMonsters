# 🏎️ DynoMonsters: The GPS Tuner RPG

**DynoMonsters** is a location-based, high-performance tuning RPG where players scavenge their real-world cities for parts, build "facsimile" monsters, and dominate the streets. 

## 🌌 The World & Factions
The world is divided into **Foundries** (Factions). Your loyalty defines your starting tech tree:
* **Arashi Foundry (Nippon):** High-RPM, Light Weight, Turbo Specialization.
* **Detroit Iron-Works (Muscle):** Displacement is King, Torque-heavy, Supercharger focus.
* **Aero-Stuttgart (Euro):** Precision Engineering, Aerodynamics, Dual-Clutch speed.

## 🛠️ Core Gameplay Loop
1. **Scavenge:** Use GPS to find "Junkyards" (Industrial zones) or "Performance Shops" (Malls/Auto zones) for parts.
2. **Tune:** Use the AI-ECU (Python-powered) to optimize your fuel maps on the Virtual Dyno.
3. **Race:** Drag race for Money and **Street Cred**.
4. **Repair/Construct:** Parts wear down. Break down Level 5 parts to craft "Prototype" components.

## 💻 Tech Stack
* **Logic Engine:** Python (FastAPI/Flask) - Handles physics, HP/TQ curves, and AI tuning.
* **Client Engine:** C# (Unity) - Handles GPS, UI, and 3D/2D visuals.
* **Data Source:** NHTSA vPIC API (for base car stats).