import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { siteConfig } from "@/lib/site";

const categories = [
  { title: "Politics", blurb: "Elections, policy, and world events." },
  { title: "Sports", blurb: "Matches, tournaments, and season outcomes." },
  { title: "Crypto", blurb: "Prices, protocols, and market moves." },
  { title: "Culture", blurb: "Awards, releases, and viral moments." },
];

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4">
          <span className="text-lg font-semibold tracking-tight">
            X<span className="text-primary">Predict</span>
          </span>
          <Link
            href="/"
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            Sign in
          </Link>
        </div>
      </header>

      <main className="flex-1">
        <section className="mx-auto w-full max-w-5xl px-4 py-16 sm:py-24">
          <div className="flex flex-col items-center text-center">
            <Badge variant="secondary" className="mb-4">
              Play-money demo
            </Badge>
            <h1 className="text-balance text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl">
              Predict the world&apos;s events.
            </h1>
            <p className="mt-4 max-w-xl text-pretty text-base text-muted-foreground sm:text-lg">
              {siteConfig.description}
            </p>
            <div className="mt-8 flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
              <Button size="lg" className="w-full sm:w-auto">
                Explore markets
              </Button>
              <Button size="lg" variant="outline" className="w-full sm:w-auto">
                How it works
              </Button>
            </div>
          </div>

          <div className="mt-16 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {categories.map((category) => (
              <Card
                key={category.title}
                className="transition-colors hover:border-primary/40"
              >
                <CardHeader>
                  <CardTitle className="text-base">{category.title}</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">
                  {category.blurb}
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex w-full max-w-5xl flex-col items-center justify-between gap-2 px-4 py-6 text-sm text-muted-foreground sm:flex-row">
          <span>
            © {new Date().getFullYear()} {siteConfig.name}
          </span>
          <span>Play money only · No real wagering</span>
        </div>
      </footer>
    </div>
  );
}
