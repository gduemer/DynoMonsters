# 🗒️ Phase 1: Prototype "The First Pull"

### 🟩 Python Tasks (The Backend)
- [ ] Create a `Car` class that stores `BaseTorque`, `Weight`, and `Redline`.
- [ ] Write a script to fetch real car data from the **NHTSA API**.
- [ ] Build the `Dyno_Generator` function:
    - Input: Engine Mods + Fuel Map.
    - Output: A JSON array of 500 data points representing the HP/TQ curve.
- [ ] Create a simple "Wear and Tear" algorithm (Parts lose 1% health per race).

### 🟦 C# Tasks (The Client)
- [ ] Setup a Unity project with a basic UI.
- [ ] Implement the **Part Class**:
    ```csharp
    public class Part {
        public string Name;
        public int Level;
        public float WeightImpact;
        public float TorqueMultiplier;
        public float Condition; // 0.0 to 1.0
    }
    ```
- [ ] Create a "Dyno View" using a line-renderer to draw the data from Python.
- [ ] Basic GPS "Ping" system to show "Junkyards" nearby on a flat map.

### 💰 Economy/Social
- [ ] Define "Street Cred" tiers (e.g., *Novice*, *Local Legend*, *Ghost of the Highway*).
- [ ] Design the "Scrap" system: 3x Common Parts = 1x Random Uncommon Part.