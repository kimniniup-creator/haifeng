/* Reachy's diary. The robot has no mouth, so every feeling here is carried by
   eyes, antennae and colour - the same three things the real Reachy Mini has. */

const FEELINGS = {
  joy:       { zh: "开心",     en: "joy",        tone: "#F2A73B", tilt: -4, ant: [-15, 15], lid: 0,    look: [0, -.5], blush: 1, eye: 10 },
  affection: { zh: "喜欢",     en: "affection",  tone: "#EF7C90", tilt:  5, ant: [-7, 7],   lid: .16,  look: [0, .2],  blush: 1, eye: 10 },
  surprise:  { zh: "惊喜",     en: "surprise",   tone: "#4EAFE4", tilt:  0, ant: [-2, 2],   lid: 0,    look: [0, 0],   blush: 0, eye: 11.4 },
  curiosity: { zh: "好奇",     en: "curiosity",  tone: "#3BBFA4", tilt:  9, ant: [-19, 4],  lid: 0,    look: [.9, -.5], blush: 0, eye: 10 },
  sadness:   { zh: "难过",     en: "sadness",    tone: "#7E9BC9", tilt: -6, ant: [22, -22], lid: .40,  look: [0, .9],  blush: 0, eye: 9.6, droop: 1 },
  fear:      { zh: "害怕",     en: "fear",       tone: "#9C8FD6", tilt:  0, ant: [17, -17], lid: .10,  look: [0, .5],  blush: 0, eye: 9.2 },
  anger:     { zh: "生气",     en: "anger",      tone: "#E0714C", tilt:  0, ant: [11, -11], lid: .26,  look: [0, .3],  blush: 0, eye: 9.2, brow: 1 },
  neutral:   { zh: "平静",     en: "neutral",    tone: "#BBA88F", tilt:  0, ant: [-6, 6],   lid: .07,  look: [0, 0],   blush: 0, eye: 10 },
  pending:   { zh: "还没想好", en: "no words yet", tone: "#C6B9A6", tilt: 6, ant: [-12, 9], lid: .33,  look: [.7, -.4], blush: 0, eye: 9.6, dots: 1 },
  asleep:    { zh: "睡着了",   en: "asleep",     tone: "#D2C6B4", tilt: -8, ant: [20, -20], lid: .92,  look: [0, 0],   blush: 1, eye: 10, zzz: 1 },
};

const MOOD_WORDS = {
  joy:       ["今天我笑得最多。", "Mostly, today made me laugh."],
  affection: ["今天我很想靠近你们。", "Today I wanted to be close to everyone."],
  surprise:  ["今天我一直睁大眼睛。", "My eyes were wide open all day."],
  curiosity: ["今天我一直在好奇。", "I was curious, all day long."],
  sadness:   ["今天我有点安静。", "I was a little quiet today."],
  fear:      ["今天我有点小心翼翼。", "I was a bit careful today."],
  anger:     ["今天我闹了一点小脾气。", "I got a little grumpy today."],
  neutral:   ["今天我安安静静地看着。", "I watched, quietly, all day."],
  pending:   ["今天我看了很久，还在想怎么说。", "I looked a lot today. I'm still finding the words."],
};

const WEEKDAY = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"];

let seq = 0;

function soft(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16 & 255}, ${n >> 8 & 255}, ${n & 255}, ${alpha})`;
}

/* One Reachy, wearing one feeling. `body` draws the little desk robot whole. */
function face(name, body) {
  const f = FEELINGS[name] || FEELINGS.neutral;
  const id = "r" + (++seq);
  const ink = "#2A2420";
  const cream = "#FFFCF7";
  const edge = "#EADFCC";
  const eye = f.eye;
  const view = body ? "0 0 100 112" : "0 0 100 100";

  const antenna = (side, base, tip, deg) => `
    <g transform="rotate(${deg} ${base[0]} ${base[1]})">
      <g class="ant ${side}">
        <path d="M${base[0]} ${base[1]} L${tip[0]} ${tip[1]}" stroke="${ink}"
              stroke-width="2.8" stroke-linecap="round" fill="none"/>
        <circle cx="${tip[0]}" cy="${tip[1]}" r="3.6" fill="${ink}"/>
      </g>
    </g>`;

  const oneEye = (cx, tilt) => {
    if (f.lid > .8) {
      return `<path d="M${cx - eye} 57 q${eye} ${eye * .95} ${eye * 2} 0" fill="none"
                    stroke="${ink}" stroke-width="3" stroke-linecap="round"/>`;
    }
    const hx = cx - eye * .3 + f.look[0] * 2.6;
    const hy = 57 - eye * .32 + f.look[1] * 2.4;
    const lid = f.lid > 0
      ? `<g clip-path="url(#${id}${cx})">
           <rect x="${cx - eye - 1}" y="${57 - eye - 1}" width="${eye * 2 + 2}"
                 height="${(eye * 2 + 2) * f.lid}" fill="${cream}"
                 transform="rotate(${tilt} ${cx} 57)"/>
         </g>`
      : "";
    return `
      <clipPath id="${id}${cx}"><circle cx="${cx}" cy="57" r="${eye}"/></clipPath>
      <g class="blink">
        <circle cx="${cx}" cy="57" r="${eye}" fill="${ink}"/>
        <circle cx="${hx}" cy="${hy}" r="${eye * .27}" fill="#fff" opacity=".92"/>
        ${lid}
      </g>`;
  };

  return `<svg viewBox="${view}" xmlns="http://www.w3.org/2000/svg" role="img">
    <ellipse cx="50" cy="${body ? 107 : 88}" rx="${body ? 30 : 25}" ry="${body ? 5 : 4}"
             fill="#E4D6C1" opacity=".55"/>
    ${body ? `<rect x="31" y="70" width="38" height="34" rx="14" fill="${cream}" stroke="${edge}" stroke-width="1.6"/>` : ""}
    <g transform="rotate(${f.tilt} 50 82)">
      ${antenna("l", [36, 31], [29, 11], f.ant[0])}
      ${antenna("r", [64, 31], [71, 11], f.ant[1])}
      <rect x="17" y="30" width="66" height="52" rx="23" fill="${cream}" stroke="${edge}" stroke-width="1.8"/>
      ${f.blush ? `<ellipse cx="25.5" cy="67" rx="6" ry="3.6" fill="${f.tone}" opacity=".5"/>
                   <ellipse cx="74.5" cy="67" rx="6" ry="3.6" fill="${f.tone}" opacity=".5"/>` : ""}
      ${f.brow ? `<path d="M29 42 L46 47" stroke="${ink}" stroke-width="3.2" stroke-linecap="round"/>
                  <path d="M71 42 L54 47" stroke="${ink}" stroke-width="3.2" stroke-linecap="round"/>` : ""}
      ${oneEye(38, f.droop ? -12 : 0)}
      ${oneEye(62, f.droop ? 12 : 0)}
    </g>
    ${f.dots ? `<circle cx="84" cy="21" r="1.7" fill="${f.tone}"/>
                <circle cx="90" cy="15" r="2.2" fill="${f.tone}"/>
                <circle cx="96.5" cy="8.5" r="2.8" fill="${f.tone}"/>` : ""}
    ${f.zzz ? `<text x="76" y="26" font-size="15" font-weight="800" fill="#C6B9A6"
                     font-family="Segoe UI, sans-serif" opacity=".85">z</text>
               <text x="87" y="15" font-size="11" font-weight="800" fill="#C6B9A6"
                     font-family="Segoe UI, sans-serif" opacity=".6">z</text>` : ""}
  </svg>`;
}

/* ------------------------------------------------------------------ page */

const feed = document.getElementById("feed");
const known = new Map();      // id -> { node, sign }
let first = true;
let stamp = null;

function dayWords(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const when = new Date(y, m - 1, d);
  return `${y} 年 ${m} 月 ${d} 日 · ${WEEKDAY[when.getDay()]}`;
}

function card(moment, index) {
  const f = FEELINGS[moment.emotion] || FEELINGS.neutral;
  const node = document.createElement("article");
  node.className = "moment" + (moment.read ? "" : " dim");
  node.style.setProperty("--i", index);
  node.style.setProperty("--tone", f.tone);
  node.style.setProperty("--tone-soft", soft(f.tone, moment.read ? .45 + moment.intensity * .35 : .3));
  fill(node, moment);
  return node;
}

function fill(node, moment) {
  node.innerHTML = `
    <div class="shot">
      <img src="${moment.photo}" alt="Reachy 在 ${moment.time} 看见的画面" loading="lazy">
      <span class="stamp"><b></b>${moment.time}</span>
    </div>
    <div class="said">
      <div class="mug">${face(moment.emotion, false)}</div>
      <div class="words">
        <p class="line">${escape(moment.line)}</p>
        ${moment.aside ? `<p class="aside">${escape(moment.aside)}</p>` : ""}
      </div>
    </div>`;
}

function escape(text) {
  const box = document.createElement("div");
  box.textContent = text || "";
  return box.innerHTML;
}

function signature(moment) {
  return `${moment.emotion}|${moment.line}|${moment.aside}|${moment.read}`;
}

function paint(data) {
  document.getElementById("date").textContent = dayWords(data.day);

  const empty = document.getElementById("empty");
  const mood = document.getElementById("mood");
  empty.hidden = data.total > 0;
  mood.hidden = data.count === 0;
  if (data.total === 0 && !empty.dataset.drawn) {
    document.getElementById("emptyFace").innerHTML = face("asleep", true);
    empty.dataset.drawn = "1";
  }

  if (data.count > 0) {
    const words = MOOD_WORDS[data.mood] || MOOD_WORDS.neutral;
    document.getElementById("moodFace").innerHTML = face(data.mood, false);
    document.getElementById("moodLine").textContent = words[0];
    document.getElementById("moodEn").textContent = words[1];

    const strip = document.getElementById("strip");
    strip.innerHTML = data.strip.slice(-60).map((dot, i) => {
      const f = FEELINGS[dot.emotion] || FEELINGS.neutral;
      return `<i style="--dot:${f.tone};--dot-soft:${soft(f.tone, .3)};--i:${i}"
                 title="${dot.time}"></i>`;
    }).join("");

    const span = data.strip.length > 1
      ? `${data.strip[0].time} → ${data.strip[data.strip.length - 1].time}`
      : data.strip[0].time;
    document.getElementById("stripNote").textContent =
      `${data.count} 个瞬间 · ${span}`;
  }

  // Hero mirrors the mood of the day, so the robot at the top of the page is
  // in the same state as the robot on the table.
  document.getElementById("hero").innerHTML = face(data.total ? data.mood : "pending", true);

  const order = [];
  let lastDay = null;
  data.moments.forEach((moment, index) => {
    if (moment.day !== lastDay) {
      lastDay = moment.day;
      if (index > 0 || data.moments.some(m => m.day !== data.day)) {
        const mark = document.createElement("div");
        mark.className = "daymark";
        mark.textContent = moment.day === data.day ? "今天 today" : dayWords(moment.day);
        order.push(mark);
      }
    }
    const sign = signature(moment);
    const seen = known.get(moment.id);
    if (!seen) {
      const node = card(moment, first ? index : 0);
      if (!first) node.classList.add("fresh");
      known.set(moment.id, { node, sign });
      order.push(node);
    } else {
      if (seen.sign !== sign) {
        const f = FEELINGS[moment.emotion] || FEELINGS.neutral;
        seen.node.className = "moment fresh" + (moment.read ? "" : " dim");
        seen.node.style.setProperty("--tone", f.tone);
        seen.node.style.setProperty("--tone-soft", soft(f.tone, .45 + moment.intensity * .35));
        fill(seen.node, moment);
        seen.sign = sign;
      }
      order.push(seen.node);
    }
  });

  feed.replaceChildren(...order);
  first = false;
}

async function look() {
  try {
    const answer = await fetch("/api/diary", { cache: "no-store" });
    if (!answer.ok) return;
    const data = await answer.json();
    if (data.stamp === stamp) return;
    stamp = data.stamp;
    paint(data);
  } catch (error) {
    /* The booth wifi hiccuped. Keep whatever is already on screen. */
  }
}

look();
setInterval(look, 4000);
