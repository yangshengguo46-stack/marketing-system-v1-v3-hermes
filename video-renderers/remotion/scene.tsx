import type {CSSProperties} from 'react';
import {
  AbsoluteFill,
  Img,
  interpolate,
  OffthreadVideo,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

export type SceneProps = {
  canvas: {width: number; height: number; fps: number};
  duration: number;
  purpose: string;
  visuals: Array<{
    file: string;
    mediaType: 'image' | 'video';
    sourceIn: number;
    fit: 'cover' | 'contain';
  }>;
  text: Array<{text: string; role: string; styleToken: string}>;
  motionIntent: string[];
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const font = '"PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", sans-serif';

const Visual = ({visual, index}: {visual: SceneProps['visuals'][number]; index: number}) => {
  const frame = useCurrentFrame();
  const {durationInFrames, fps} = useVideoConfig();
  const scale = interpolate(frame, [0, durationInFrames], [1.04 + index * 0.01, 1.13], clamp);
  const common: CSSProperties = {
    width: '100%',
    height: '100%',
    objectFit: visual.fit,
    transform: `scale(${scale}) translateX(${index % 2 === 0 ? -index * 8 : index * 8}px)`,
    opacity: index === 0 ? 1 : Math.max(0.2, 0.58 - index * 0.1),
    filter: index === 0 ? 'saturate(.9) contrast(1.08)' : 'saturate(.75) contrast(1.15)',
  };
  if (visual.mediaType === 'video') {
    return (
      <OffthreadVideo
        muted
        src={staticFile(visual.file)}
        startFrom={Math.round(visual.sourceIn * fps)}
        style={common}
      />
    );
  }
  return <Img src={staticFile(visual.file)} style={common} />;
};

export const MarketingScene = (props: SceneProps) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();
  const enter = spring({frame, fps, config: {damping: 18, stiffness: 130, mass: 0.8}});
  const exit = interpolate(frame, [Math.max(0, durationInFrames - 8), durationInFrames], [1, 0], clamp);
  const progress = interpolate(frame, [0, Math.max(1, durationInFrames - 1)], [0, 100], clamp);
  const accent = '#f4df4e';
  const headline = props.text.find((item) => item.role === 'headline') || props.text[0];
  const body = props.text.find((item) => item.role !== 'headline') || props.text[1];
  const hasData = props.motionIntent.includes('data_visualization');
  const inset = Math.round(Math.min(width, height) * 0.06);

  return (
    <AbsoluteFill style={{backgroundColor: '#0b1110', color: '#fffaf0', fontFamily: font, opacity: exit}}>
      {props.visuals.map((visual, index) => (
        <AbsoluteFill key={`${visual.file}-${index}`}>
          <Visual visual={visual} index={index} />
        </AbsoluteFill>
      ))}
      <AbsoluteFill
        style={{
          background: `linear-gradient(180deg, rgba(4,8,7,.12), rgba(4,8,7,.28) 42%, rgba(4,8,7,.94)), radial-gradient(circle at 78% 18%, ${accent}55, transparent 34%)`,
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.14,
          backgroundImage: `linear-gradient(${accent}66 1px, transparent 1px), linear-gradient(90deg, ${accent}66 1px, transparent 1px)`,
          backgroundSize: `${Math.round(width / 12)}px ${Math.round(width / 12)}px`,
        }}
      />

      <div style={{position: 'absolute', left: inset, right: inset, top: inset, display: 'flex', justifyContent: 'space-between', fontSize: Math.round(width * 0.022), letterSpacing: 4, fontWeight: 750}}>
        <span style={{padding: '12px 18px', border: `1px solid ${accent}99`, borderRadius: 999, background: 'rgba(8,12,11,.36)'}}>MARKETING OS</span>
        <span>{props.purpose.slice(0, 36).toUpperCase()}</span>
      </div>

      <div style={{position: 'absolute', left: inset, right: inset, bottom: Math.round(height * 0.1), transform: `translateY(${interpolate(enter, [0, 1], [70, 0])}px)`, opacity: enter}}>
        {headline ? (
          <div style={{fontSize: Math.round(width * 0.09), lineHeight: 1.04, letterSpacing: -3, fontWeight: 900, textShadow: '0 6px 34px rgba(0,0,0,.35)'}}>
            {headline.text}
          </div>
        ) : null}
        {body ? (
          <div style={{fontSize: Math.round(width * 0.032), lineHeight: 1.55, fontWeight: 560, opacity: 0.84, marginTop: 30, maxWidth: '88%'}}>
            {body.text}
          </div>
        ) : null}
        {hasData ? (
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginTop: 38}}>
            {[37, 68, 92].map((value, index) => (
              <div key={value} style={{padding: '22px 20px', border: '1px solid rgba(255,255,255,.25)', background: 'rgba(4,8,7,.54)'}}>
                <div style={{fontSize: Math.round(width * 0.045), fontWeight: 900, color: index === 1 ? accent : '#fffaf0'}}>{Math.round(value * enter)}%</div>
                <div style={{fontSize: Math.round(width * 0.016), letterSpacing: 2, opacity: 0.6, marginTop: 8}}>SIGNAL {index + 1}</div>
              </div>
            ))}
          </div>
        ) : null}
        <div style={{height: 6, marginTop: 42, background: 'rgba(255,255,255,.18)', overflow: 'hidden'}}>
          <div style={{height: '100%', width: `${progress}%`, background: accent, boxShadow: `0 0 20px ${accent}`}} />
        </div>
      </div>
    </AbsoluteFill>
  );
};
