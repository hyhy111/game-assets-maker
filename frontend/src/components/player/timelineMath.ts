export function frameFromTimelineRatio(ratio: number, totalFrames: number): number {
  const lastFrame = Math.max(totalFrames - 1, 0);
  const clampedRatio = Math.max(0, Math.min(1, ratio));
  return Math.round(clampedRatio * lastFrame);
}

export function timelineFramePercent(frame: number, totalFrames: number): number {
  if (totalFrames <= 1) return 0;
  const lastFrame = totalFrames - 1;
  return (Math.max(0, Math.min(lastFrame, frame)) / lastFrame) * 100;
}

interface TimelinePositionedFrame {
  timeline_index?: number;
}

export function timelineFrameForVisibleIndex(
  frames: TimelinePositionedFrame[],
  visibleIndex: number,
): number {
  return frames[visibleIndex]?.timeline_index ?? visibleIndex;
}

export function nearestVisibleFrameIndex(
  frames: TimelinePositionedFrame[],
  timelineFrame: number,
): number {
  if (frames.length === 0) return 0;
  let nearestIndex = 0;
  let nearestDistance = Number.POSITIVE_INFINITY;
  frames.forEach((frame, index) => {
    const distance = Math.abs((frame.timeline_index ?? index) - timelineFrame);
    if (distance <= nearestDistance) {
      nearestIndex = index;
      nearestDistance = distance;
    }
  });
  return nearestIndex;
}

export function sourceFrameFromTimelineFrame(
  timelineFrame: number,
  sourceStartFrame: number,
  frameInterval: number,
): number {
  return sourceStartFrame + timelineFrame * Math.max(1, frameInterval);
}
