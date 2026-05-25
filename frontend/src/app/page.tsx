import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import { Hero } from "@/components/marketing/Hero";
import { Ticker } from "@/components/marketing/Ticker";
import { FinalCta } from "@/components/marketing/FinalCta";
import { LiveMarkets } from "@/components/markets/LiveMarkets";
import { ExperimentalMarkets } from "@/components/experimental/ExperimentalMarkets";
import { RealtimeIdentity } from "@/components/social/RealtimeIdentity";
import { WhiteLabel } from "@/components/whitelabel/WhiteLabel";
import { Reveal } from "@/components/ui/Reveal";

export default function Home() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <Ticker />
        <Reveal>
          <LiveMarkets />
        </Reveal>
        <Reveal>
          <ExperimentalMarkets />
        </Reveal>
        <Reveal>
          <RealtimeIdentity />
        </Reveal>
        <Reveal>
          <WhiteLabel />
        </Reveal>
        <FinalCta />
      </main>
      <Footer />
    </>
  );
}
