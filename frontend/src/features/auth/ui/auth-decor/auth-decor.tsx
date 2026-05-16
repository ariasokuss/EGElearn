"use client";

import {
  AUTH_DECOR_OUTER_CLASSNAME,
  AUTH_DECOR_OUTER_STYLE,
  AUTH_ILLUSTRATION_SRC,
} from "./auth-decor-shell";

const EMPTY_IMAGE_SRC =
  "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";

export function AuthDecor() {
  return (
    <div className={AUTH_DECOR_OUTER_CLASSNAME} style={AUTH_DECOR_OUTER_STYLE}>
      <div className="relative min-h-0 flex-1">
        {/* <div className="absolute inset-0 flex items-center justify-start overflow-hidden">
          <div className="relative h-full min-h-0 w-[80%] max-w-[80%]">
            <Image
              src="/auth/bg_nl_auth.svg"
              alt=""
              fill
              className="object-contain object-left"
              unoptimized
            />
          </div>
        </div> */}
        <div className="absolute inset-0 flex items-center justify-start px-6 pt-6 pb-[calc(1.5rem-120px)] lg:px-8 lg:pt-8 lg:pb-[calc(2rem-120px)] xl:px-10 xl:pt-10 xl:pb-[calc(2.5rem-120px)]">
          <div className="relative aspect-[1372/797] h-[80vh] max-w-[260%] xl:h-[85vh] 2xl:h-[80vh]">
            <picture className="absolute inset-0 block">
              <source
                media="(min-width: 1024px)"
                srcSet={AUTH_ILLUSTRATION_SRC}
                sizes="(min-width: 1280px) 50vw, 45vw"
              />
              <img
                src={EMPTY_IMAGE_SRC}
                alt="NovaLearn"
                loading="eager"
                fetchPriority="high"
                decoding="async"
                className="h-full w-full object-contain drop-shadow-lg"
              />
            </picture>
          </div>
        </div>
      </div>
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-[120px] rounded-b-[24px]"
        style={{
          background:
            "linear-gradient(to top, rgba(246, 246, 246, 1), rgba(246, 246, 246, 0))",
        }}
      />
    </div>
  );
}
