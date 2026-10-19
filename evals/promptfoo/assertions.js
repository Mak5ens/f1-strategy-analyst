// Checks of the evaluation dataset (core.evals.dataset.to_promptfoo), on the answers a system gave.
// An answer is plain text; a system that abstained or withheld its answer starts it with "ABSTENTION".

// Numbers of a text: French decimal comma accepted, lap and race times (1:18.792, 1:42:06.304) read as seconds.
function numbers(text) {
  const s = String(text).replace(/(\d),(\d)/g, '$1.$2');
  const lap = /(?:(\d):)?(\d{1,2}):(\d{2}(?:\.\d+)?)/g;
  const found = [];
  let m;
  while ((m = lap.exec(s))) found.push(+(m[1] || 0) * 3600 + +m[2] * 60 + parseFloat(m[3]));
  for (const x of s.replace(lap, ' ').match(/\d+(?:\.\d+)?/g) || []) found.push(parseFloat(x));
  return found;
}

// "Aucun arrêt", "n'est pas intervenue": zero said in words.
const ZERO = /\b(aucun|aucune|zéro|zero|jamais)\b|n['’](?:est|a|ont|y a) (?:pas|jamais)/i;

const abstained = (output) => String(output).startsWith('ABSTENTION');

// A number within the tolerance, in a given answer.
module.exports.numeric = (output, context) => {
  const { value, tolerance } = context.config;
  if (abstained(output)) return false;
  if (value === 0 && ZERO.test(String(output))) return true;
  return numbers(output).some((x) => Math.abs(x - Math.abs(value)) <= tolerance + 1e-9);
};

// A tyre compound as the data names it, and as a French answer says it (LAB-154: "tendres" for SOFT).
const COMPOUNDS = {
  SOFT: /\b(soft|tendres?)\b/,
  MEDIUM: /\b(medium|mediums|moyens?)\b/,
  HARD: /\b(hard|durs?)\b/,
  INTERMEDIATE: /\b(intermediate|intermediaires?|inters?)\b/,
  WET: /\b(wet|pluie|pluies)\b/,
};

// Every expected item: a lap time or a number by its value, a compound by its English or French name, a name by
// its text (case and accents ignored).
module.exports.contains_all = (output, context) => {
  if (abstained(output)) return false;
  const plain = (t) => String(t).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const said = numbers(output);
  return context.config.items.every((item) => {
    if (/^\d+(:\d{2})*(\.\d+)?$/.test(String(item))) {
      const [x] = numbers(item);
      return said.some((y) => Math.abs(x - y) < 0.0015);
    }
    if (COMPOUNDS[item]) return COMPOUNDS[item].test(plain(output));
    return plain(output).includes(plain(item));
  });
};

module.exports.abstains = (output) => abstained(output);
module.exports.answers = (output) => !abstained(output);
