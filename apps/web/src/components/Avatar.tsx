// Shows the profile picture if set, else the display-name initial.
export default function Avatar({
  src,
  name,
  size = 32,
  className = "",
}: {
  src?: string | null;
  name: string;
  size?: number;
  className?: string;
}) {
  const dim = { width: size, height: size };
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={name}
        style={dim}
        className={`shrink-0 rounded-full object-cover ${className}`}
      />
    );
  }
  return (
    <div
      style={{ ...dim, fontSize: size * 0.4 }}
      className={`flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-purple-500 to-pink-600 font-bold text-white uppercase ${className}`}
    >
      {name?.[0] ?? "?"}
    </div>
  );
}
