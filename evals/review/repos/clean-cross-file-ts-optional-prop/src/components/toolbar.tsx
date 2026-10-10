import { Button } from "./button";

export function Toolbar({ undo }: { undo: () => void }) {
  return <Button label="Undo" onClick={undo} size="sm" />;
}
