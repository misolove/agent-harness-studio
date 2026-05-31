function extractJsonMessageFragment(text) {
  const source = String(text || "");
  const fieldIndex = source.indexOf('"message"');
  if (fieldIndex < 0) return null;

  const colonIndex = source.indexOf(":", fieldIndex + 9);
  if (colonIndex < 0) return null;

  const quoteIndex = source.indexOf('"', colonIndex + 1);
  if (quoteIndex < 0) return null;

  let output = "";
  for (let index = quoteIndex + 1; index < source.length; index += 1) {
    const char = source[index];
    if (char === '"') break;
    if (char === "\\" && index + 1 < source.length) {
      const escaped = source[index + 1];
      if (escaped === "n") {
        output += "\n";
        index += 1;
        continue;
      }
      if (escaped === "t") {
        output += "\t";
        index += 1;
        continue;
      }
      if (escaped === "r") {
        index += 1;
        continue;
      }
      if (escaped === '"' || escaped === "\\" || escaped === "/") {
        output += escaped;
        index += 1;
        continue;
      }
    }
    output += char;
  }

  return output.trim() || null;
}

function normalizeMolderMessage(data) {
  const message = String(data?.message || "");
  const trimmed = message.trim();
  if (!trimmed.startsWith("{") || !trimmed.includes('"message"')) {
    return message;
  }

  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && typeof parsed.message === "string") {
      return parsed.message;
    }
  } catch {
    const recovered = extractJsonMessageFragment(trimmed);
    if (recovered) {
      return `${recovered}\n\n(응답이 길어 일부가 잘렸습니다. 더 좁은 범위로 다시 물어보면 이어서 정리할 수 있어요.)`;
    }
  }

  return "응답 형식을 정리하지 못했습니다. 질문 범위를 조금 좁혀서 다시 말씀해주세요.";
}

export default normalizeMolderMessage;
export { extractJsonMessageFragment };
