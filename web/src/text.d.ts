// htmx's file is bundled as text (wrangler.toml's rule for it), to be served from the Worker
declare module "htmx.org/dist/htmx.min.js" {
  const text: string;
  export default text;
}
