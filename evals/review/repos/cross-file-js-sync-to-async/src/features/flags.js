const FLAGS_URL = "https://flags.internal/api/flags";

export async function loadFlags() {
  const response = await fetch(FLAGS_URL);
  return response.json();
}
