declare module "@cycjimmy/jsmpeg-player" {
  interface VideoElementOptions {
    canvas?: HTMLCanvasElement;
  }
  interface PlayerOptions {
    audio?: boolean;
    videoBufferSize?: number;
  }
  class VideoElement {
    constructor(
      container: HTMLElement,
      url: string,
      options?: VideoElementOptions,
      playerOptions?: PlayerOptions,
    );
    destroy(): void;
  }
  export default { VideoElement };
}
