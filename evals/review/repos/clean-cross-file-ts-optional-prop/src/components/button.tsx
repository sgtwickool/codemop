type ButtonProps = { label: string; onClick: () => void; size?: "sm" | "md" };

export function Button({ label, onClick, size = "md" }: ButtonProps) {
  return (
    <button className={size === "sm" ? "btn btn-sm" : "btn"} onClick={onClick}>
      {label}
    </button>
  );
}
