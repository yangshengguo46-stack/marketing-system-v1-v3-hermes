import {Composition} from 'remotion';
import {MarketingScene, type SceneProps} from './scene';

const defaults: SceneProps = {
  canvas: {width: 1080, height: 1920, fps: 30},
  duration: 1,
  purpose: 'Marketing scene',
  visuals: [],
  text: [],
  motionIntent: [],
};

export const VideoRendererRoot = () => (
  <Composition
    id="MarketingScene"
    component={MarketingScene}
    defaultProps={defaults}
    durationInFrames={30}
    fps={30}
    width={1080}
    height={1920}
    calculateMetadata={({props}) => ({
      durationInFrames: Math.max(1, Math.ceil(props.duration * props.canvas.fps)),
      fps: props.canvas.fps,
      width: props.canvas.width,
      height: props.canvas.height,
    })}
  />
);
