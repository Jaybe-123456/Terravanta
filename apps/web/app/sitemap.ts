import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL || "https://terravanta-five.vercel.app").replace(/\/$/, "");
  return [{
    url: `${siteUrl}/product`,
    changeFrequency: "monthly",
    priority: 0.8,
  }];
}
