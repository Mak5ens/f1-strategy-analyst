// A number as a text writes it: 24.8, 0,0192, 1:20.901, 17.
const NUMBER = /(\d+(?:[:.,]\d+)*)/;

/** A text whose numbers stand out: each one comes from an analysis, and the eye finds them first. */
export function FiguresText({ text }: { text: string }) {
  return (
    <>
      {text.split(NUMBER).map((part, index) =>
        index % 2 ? (
          // biome-ignore lint/suspicious/noArrayIndexKey: the parts of a fixed text, in order
          <span key={index} className="figures font-semibold text-foreground">
            {part}
          </span>
        ) : (
          part
        ),
      )}
    </>
  );
}
