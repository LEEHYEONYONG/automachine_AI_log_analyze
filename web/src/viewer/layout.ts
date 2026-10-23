// Scene layout in arbitrary units: x runs along the conveyor, y is up, z is depth (negative = back).

export const STATION_X: Record<string, number> = {
  INFEED: -4.8,
  VISION: -2.4,
  DISPENSER: 0,
  INSPECTION: 2.4,
  OUTFEED: 4.8,
};
export const STATION_ORDER = ["INFEED", "VISION", "DISPENSER", "INSPECTION", "OUTFEED"];
export const STATION_SPACING = 2.4;
export const UPSTREAM_X = STATION_X.INFEED - STATION_SPACING; // end of the previous machine's conveyor
export const DOWNSTREAM_X = STATION_X.OUTFEED + STATION_SPACING; // start of the next machine's conveyor

export const FLOOR_Y = -1.15;
export const FRAME = { x: 6.85, zBack: -2.65, zFront: 2.05, height: 2.6 };
export const BELT_TOP = 0.15;
export const PART = { w: 0.7, h: 0.06, d: 0.36 };
export const PART_Y = BELT_TOP + PART.h / 2;
export const PART_TOP = BELT_TOP + PART.h;
export const BACK_Z = -1.3; // NG buffer sits behind the belt
export const HEAD_HIGH = 1.1;

// Each station has its own short conveyor zone: two narrow edge belts under the part's long
// edges, with the centre left open for a stopper and, where needed, a lift-up unit.
export const ZONE_LEN = 2.1;
export const LANE_Z = 0.14;
export const LANE_W = 0.07;
export const LIFT_H = 0.05; // how far a lift-up unit raises the part off the belts

export const COLORS = {
  table: "#36414c",
  frame: "#5d6b79",
  steel: "#9aa7b4",
  belt: "#161c22",
  part: "#c9d2db",
  bead: "#e8a33d",
  accent: "#3987e5",
  ok: "#2fbf71",
  ng: "#e5484d",
  warn: "#e8a33d",
  idle: "#4a5866",
};

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

// Adhesive bead: a rectangle drawn just inside the housing edge, starting at the back-left corner.
const BW = 0.58;
const BD = 0.24;
export const BEAD_SEGMENTS: { from: [number, number]; to: [number, number] }[] = [
  { from: [-BW / 2, -BD / 2], to: [BW / 2, -BD / 2] },
  { from: [BW / 2, -BD / 2], to: [BW / 2, BD / 2] },
  { from: [BW / 2, BD / 2], to: [-BW / 2, BD / 2] },
  { from: [-BW / 2, BD / 2], to: [-BW / 2, -BD / 2] },
];
const LENGTHS = BEAD_SEGMENTS.map((s) => Math.hypot(s.to[0] - s.from[0], s.to[1] - s.from[1]));
export const BEAD_TOTAL = LENGTHS.reduce((a, b) => a + b, 0);
export const BEAD_STARTS = LENGTHS.map((_, i) => LENGTHS.slice(0, i).reduce((a, b) => a + b, 0));
export const BEAD_LENGTHS = LENGTHS;

/** Point on the bead path (x, z relative to the part centre) at fraction f of its length. */
export function beadPoint(f: number): [number, number] {
  let d = Math.min(Math.max(f, 0), 1) * BEAD_TOTAL;
  for (let i = 0; i < BEAD_SEGMENTS.length; i++) {
    if (d <= LENGTHS[i] || i === BEAD_SEGMENTS.length - 1) {
      const s = BEAD_SEGMENTS[i];
      const t = LENGTHS[i] ? d / LENGTHS[i] : 0;
      return [lerp(s.from[0], s.to[0], t), lerp(s.from[1], s.to[1], t)];
    }
    d -= LENGTHS[i];
  }
  return BEAD_SEGMENTS[0].from;
}
