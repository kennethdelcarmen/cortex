function pad(value: number) {
  return String(value).padStart(2, "0");
}

export function currentLocalDateInput(now = new Date()) {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
