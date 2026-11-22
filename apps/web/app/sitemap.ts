import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL || "https://terravanta-five.vercel.app").replace(/\/$/, "");
  return [
    { url: `${siteUrl}/product`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${siteUrl}/privacy`, changeFrequency: "yearly", priority: 0.3 },
    { url: `${siteUrl}/terms`, changeFrequency: "yearly", priority: 0.3 },
    { url: `${siteUrl}/data-deletion`, changeFrequency: "yearly", priority: 0.3 },
  ];
}
