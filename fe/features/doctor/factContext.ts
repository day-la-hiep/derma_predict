/** Phần ngữ cảnh của một dữ kiện lấy từ graph theo dõi: vị trí, mốc khởi phát và phủ định ("người bệnh nói không có"). */
export interface FactContext {
  present?: boolean;
  siteText?: string | null;
  onsetText?: string | null;
}

export function isAbsentFact(fact: FactContext): boolean {
  return fact.present === false;
}

export function describeFactContext(fact: FactContext): string {
  const parts: string[] = [];
  if (fact.siteText) parts.push(`vị trí: ${fact.siteText}`);
  if (fact.onsetText) parts.push(`khởi phát: ${fact.onsetText}`);
  return parts.join(" · ");
}
