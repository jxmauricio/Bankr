import { useEffect, useState, type RefObject } from "react";
import { Keyboard, LayoutAnimation, Platform, type KeyboardEvent, type View } from "react-native";

/**
 * How far the keyboard overlaps `ref`'s view, measured on screen, so the
 * view can pad its bottom by exactly that much. Unlike KeyboardAvoidingView,
 * this doesn't care where the view sits (below a header, above a tab bar).
 * Pad the measured view itself: its frame stays put, only its content moves.
 *
 * Android's default "resize" mode already shrinks the window for the
 * keyboard, so there the overlap measures 0 and this is a no-op.
 */
export function useKeyboardInset(ref: RefObject<View | null>): number {
  const [inset, setInset] = useState(0);

  useEffect(() => {
    const ios = Platform.OS === "ios";

    // Move in step with the keyboard's own animation.
    function animate(e: KeyboardEvent) {
      if (!e.duration) return;
      LayoutAnimation.configureNext({
        duration: e.duration,
        update: { duration: e.duration, type: LayoutAnimation.Types.keyboard },
      });
    }

    const show = Keyboard.addListener(ios ? "keyboardWillShow" : "keyboardDidShow", (e) => {
      ref.current?.measureInWindow((_x, y, _width, height) => {
        animate(e);
        setInset(Math.max(0, y + height - e.endCoordinates.screenY));
      });
    });
    const hide = Keyboard.addListener(ios ? "keyboardWillHide" : "keyboardDidHide", (e) => {
      animate(e);
      setInset(0);
    });
    return () => {
      show.remove();
      hide.remove();
    };
  }, [ref]);

  return inset;
}
