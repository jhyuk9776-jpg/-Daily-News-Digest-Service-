export interface RelatedLink {
  source: string;
  link: string;
}

export interface DigestItem {
  title: string;
  bullets: string[];
  source: string;
  link: string;
  related_links: RelatedLink[];
}

export interface DigestCategory {
  name: string;
  items: DigestItem[];
}

export interface Digest {
  date: string;
  categories: DigestCategory[];
}
