// O backend envia timestamps em UTC SEM sufixo de fuso (ex.: "2026-07-14T19:44:19").
// new Date() interpretaria essa string como horário LOCAL, deslocando o horário
// exibido (aparecia ~3h adiantado no Brasil). Estas funções garantem a
// interpretação como UTC antes de converter para o fuso do usuário.

function asUTC(dt: string): Date {
  // Se já vier com Z ou offset (+/-hh:mm), respeita; senão trata como UTC.
  const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(dt) ? dt : dt + "Z";
  return new Date(iso);
}

export function fmtDateTime(dt: string | null | undefined): string {
  if (!dt) return "";
  return asUTC(dt).toLocaleString("pt-BR");
}

export function fmtDate(dt: string | null | undefined): string {
  if (!dt) return "";
  return asUTC(dt).toLocaleDateString("pt-BR");
}

export function utcMs(dt: string | null | undefined): number {
  if (!dt) return 0;
  return asUTC(dt).getTime();
}
