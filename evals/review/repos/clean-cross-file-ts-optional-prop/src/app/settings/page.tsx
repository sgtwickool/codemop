import { Button } from "@/components/button";

export default function Settings({ save }: { save: () => void }) {
  return <Button label="Save" onClick={save} />;
}
