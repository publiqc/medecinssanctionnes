import type { Lang } from "../lib/types";

export const defaultLang: Lang = "fr";

/** Locale-prefixed base path ("" for FR at root, "/en" for English). */
export const basePath: Record<Lang, string> = { fr: "", en: "/en" };

/** URL of a doctor detail page for a given locale. */
export function doctorHref(lang: Lang, slug: string): string {
  return lang === "en" ? `/en/doctor/${slug}` : `/medecin/${slug}`;
}

/** Same page in the other language (used by the language switcher). */
export const otherLang: Record<Lang, Lang> = { fr: "en", en: "fr" };

export const ui = {
  fr: {
    "site.brand": "Médecins sanctionnés",
    "site.lang": "fr",
    "lang.switch": "English",
    "nav.back": "Retour à la recherche",

    "strip.updated": "Données mises à jour le",
    "strip.source": "Source :",
    "source.name": "Collège des médecins du Québec",

    "home.title": "Médecins sanctionnés au Québec",
    "home.subtitle":
      "Radiations, suspensions et limitations d’exercice des médecins du Québec.",
    "home.searchPlaceholder": "Rechercher un médecin…",
    "home.searchClear": "Effacer la recherche",
    "home.recent": "Sanctions récentes",
    "home.results": "Résultats",
    "home.empty": "Aucun résultat.",
    "home.searching": "Recherche en cours…",
    "list.title": "Tous les médecins visés",
    "list.browseAll": "Voir tous les médecins",
    "list.count": "médecins visés",
    "pagination.prev": "Précédent",
    "pagination.next": "Suivant",
    "pagination.page": "Page",
    "pagination.of": "de",
    "home.metaDescription":
      "Radiations, suspensions et limitations d’exercice des médecins du Québec, d’après le bottin public du Collège des médecins du Québec.",

    "stats.doctors": "Médecins visés",
    "stats.radiations": "Radiations",
    "stats.suspensions": "Suspensions",
    "stats.limitations": "Limitations",

    "status.radiated": "Radiés ou suspendus",
    "status.restricted": "Exercice limité",
    "status.record": "Antécédent disciplinaire",

    "detail.memberSince": "Membre du Collège depuis",
    "detail.specialistSince": "Spécialiste depuis",
    "detail.deceased": "Décédé(e)",
    "detail.history": "Historique disciplinaire",
    "detail.inEffect": "En vigueur",
    "detail.served": "Purgée",
    "detail.duration": "Durée :",
    "detail.start": "Début :",
    "detail.end": "Fin :",
    "detail.estimated": "(estimée)",
    "detail.noticeLabel": "",
    "detail.notices": "Avis publiés",
    "detail.noticePublished": "Avis publié le",
    "detail.noticeSource": "Avis publié au bottin du Collège des médecins du Québec.",
    "detail.sources": "Sources",
    "detail.officialRecord": "Fiche officielle au bottin du CMQ",
    "detail.decision": "Décision",
    "decision.heading": "Décisions du conseil de discipline",
    "decision.fileLabel": "Dossier",
    "decision.grounds": "Motif",
    "decision.disposition": "Sanction imposée",
    "status.formerlyStruckOff": "A déjà été radié (sanction purgée)",
    "decision.ban": "Ordonnance de non-publication : l’identité du patient est protégée.",
    "decision.showCharges": "Voir les chefs reprochés",
    "decision.chargesLabel": "Chefs reprochés (extrait de la décision)",
    "decision.chargesNote": "Texte reproduit de la décision du conseil de discipline. Des erreurs de reconnaissance de texte peuvent subsister ; consultez la décision officielle.",
    "decision.viewDecision": "Consulter la décision",
    "detail.sourceNote":
      "Les textes ci-dessus sont reproduits des avis publics du CMQ. Les dates de fin marquées « estimée » sont calculées à partir de la durée indiquée dans la décision.",
    "detail.metaDescription": "Dossier disciplinaire public de",

    "footer.noticeStrong": "Avis.",
    "footer.noticeBefore":
      "Ce site reproduit des renseignements publics publiés par le Collège des médecins du Québec dans son bottin des médecins. Les textes des avis et des décisions y sont reproduits intégralement. Une sanction temporaire peut déjà avoir été purgée. Veuillez toujours consulter le",
    "footer.officialLink": "bottin officiel du CMQ",
    "footer.noticeAfter": "pour connaître le statut actuel d’un médecin.",
    "footer.errorPrompt":
      "Vous avez remarqué une erreur ou souhaitez demander une rectification ?",
    "footer.contact": "Écrivez-nous",

    "contact.title": "Nous joindre",
    "contact.intro":
      "Ce site reproduit des renseignements publics publiés par le Collège des médecins du Québec. Nous tenons à ce qu’ils soient exacts et à jour.",
    "contact.errorHeading": "Signaler une erreur",
    "contact.errorBody":
      "Si un renseignement vous semble inexact ou incomplet, ou si vous souhaitez demander une rectification, écrivez-nous. Indiquez le nom, le numéro de permis et la correction demandée.",
    "contact.sourceHeading": "Code source et données",
    "contact.sourceBody":
      "Ce projet est ouvert et transparent : le code et les données qui servent à produire ce site sont accessibles publiquement.",
    "contact.sourceCta": "Voir le projet sur GitHub",
    "contact.feedbackHeading": "Commentaires et bogues",
    "contact.feedbackBody":
      "Pour un commentaire général ou pour signaler un problème technique, ouvrez un ticket sur GitHub.",
    "contact.feedbackCta": "Ouvrir un ticket",

    "footer.about": "À propos",
    "about.title": "À propos et méthodologie",
    "about.intro":
      "Ce site rassemble en un seul endroit consultable les médecins du Québec ayant fait l’objet d’une sanction disciplinaire. Il vise la transparence et la protection du public.",
    "about.sourceHeading": "Source des données",
    "about.sourceBody":
      "Toutes les données proviennent des registres publics du Collège des médecins du Québec : le bottin des médecins et les décisions des conseils de discipline. Les textes officiels (chefs reprochés et sanctions) sont reproduits mot pour mot, sans reformulation, et chaque fiche renvoie à la décision officielle.",
    "about.methodHeading": "Comment les données sont recueillies",
    "about.methodBody":
      "Les renseignements sont recueillis automatiquement à partir des services publics du CMQ, puis mis à jour chaque semaine à partir des avis publiés (radiation, limitation, suspension, révocation de permis). La collecte est faite de façon mesurée et s’identifie honnêtement.",
    "about.scopeHeading": "Ce que nous incluons",
    "about.scopeBody":
      "Nous n’affichons que les médecins ayant fait l’objet d’une conclusion disciplinaire réelle. Les plaintes rejetées ou retirées ne sont jamais présentées. Les radiations administratives pour non-paiement de la cotisation ne sont pas des sanctions disciplinaires et sont exclues.",
    "about.privacyHeading": "Respect de la vie privée",
    "about.privacyBody":
      "Par respect de la vie privée, nous n’affichons que la ville d’exercice; nous ne publions ni adresse ni numéro de téléphone. Les ordonnances de non-publication qui protègent l’identité des patients sont respectées.",
    "about.accuracyHeading": "Exactitude et limites",
    "about.accuracyBody":
      "Le registre du CMQ ne montre que les sanctions en cours : une radiation temporaire déjà purgée en disparaît. Nous la retrouvons dans le texte de la décision et l’indiquons comme purgée. Certaines décisions plus anciennes ne sont accessibles que par un lien externe.",
    "about.correctionsHeading": "Signaler une erreur",
    "about.correctionsBody":
      "Nous tenons à l’exactitude des renseignements. Pour signaler une erreur ou demander une rectification, écrivez-nous.",
    "about.correctionsCta": "Nous joindre",
    "about.independenceHeading": "Indépendance",
    "about.independenceBody":
      "Ce site est indépendant. Il n’est ni affilié au Collège des médecins du Québec ni approuvé par celui-ci.",
  },
  en: {
    "site.brand": "Sanctioned Doctors",
    "site.lang": "en",
    "lang.switch": "Français",
    "nav.back": "Back to search",

    "strip.updated": "Data updated on",
    "strip.source": "Source:",
    "source.name": "Collège des médecins du Québec",

    "home.title": "Sanctioned Doctors in Quebec",
    "home.subtitle":
      "Strikings off, suspensions and practice restrictions of Quebec physicians.",
    "home.searchPlaceholder": "Search for a doctor…",
    "home.searchClear": "Clear search",
    "home.recent": "Recent sanctions",
    "home.results": "Results",
    "home.empty": "No results.",
    "home.searching": "Searching…",
    "list.title": "All listed doctors",
    "list.browseAll": "Browse all doctors",
    "list.count": "listed doctors",
    "pagination.prev": "Previous",
    "pagination.next": "Next",
    "pagination.page": "Page",
    "pagination.of": "of",
    "home.metaDescription":
      "Strikings off, suspensions and practice restrictions of Quebec physicians, based on the public directory of the Collège des médecins du Québec.",

    "stats.doctors": "Doctors listed",
    "stats.radiations": "Strikings off",
    "stats.suspensions": "Suspensions",
    "stats.limitations": "Restrictions",

    "status.radiated": "Struck off or suspended",
    "status.restricted": "Restricted practice",
    "status.record": "Disciplinary record",

    "detail.memberSince": "Member of the Collège since",
    "detail.specialistSince": "Specialist since",
    "detail.deceased": "Deceased",
    "detail.history": "Disciplinary history",
    "detail.inEffect": "In effect",
    "detail.served": "Served",
    "detail.duration": "Duration:",
    "detail.start": "Start:",
    "detail.end": "End:",
    "detail.estimated": "(estimated)",
    "detail.noticeLabel": "Original notice (in French)",
    "detail.notices": "Published notices",
    "detail.noticePublished": "Notice published on",
    "detail.noticeSource": "Notice published in the Collège des médecins du Québec directory.",
    "detail.sources": "Sources",
    "detail.officialRecord": "Official CMQ directory record",
    "detail.decision": "Decision",
    "decision.heading": "Disciplinary council decisions",
    "decision.fileLabel": "File",
    "decision.grounds": "Grounds",
    "decision.disposition": "Sanction imposed",
    "status.formerlyStruckOff": "Previously struck off (sanction served)",
    "decision.ban": "Non-publication order: the patient’s identity is protected.",
    "decision.showCharges": "View the charges",
    "decision.chargesLabel": "Charges (excerpt from the decision)",
    "decision.chargesNote": "Text reproduced from the disciplinary council’s decision. Minor text-recognition errors may remain; consult the official decision.",
    "decision.viewDecision": "View the decision",
    "detail.sourceNote":
      "The texts above are reproduced from the CMQ’s public notices. End dates marked “estimated” are calculated from the duration stated in the decision.",
    "detail.metaDescription": "Public disciplinary record of",

    "footer.noticeStrong": "Notice.",
    "footer.noticeBefore":
      "This site reproduces public information published by the Collège des médecins du Québec in its physician directory. Notices and decisions are reproduced in full. A temporary sanction may already have been served. Always consult the",
    "footer.officialLink": "official CMQ directory",
    "footer.noticeAfter": "to confirm a physician’s current status.",
    "footer.errorPrompt": "Noticed an error or want to request a correction?",
    "footer.contact": "Contact us",

    "contact.title": "Contact",
    "contact.intro":
      "This site reproduces public information published by the Collège des médecins du Québec. We want it to be accurate and up to date.",
    "contact.errorHeading": "Report an error",
    "contact.errorBody":
      "If a piece of information looks inaccurate or incomplete, or you would like to request a correction, write to us. Please include the name, permit number, and the correction requested.",
    "contact.sourceHeading": "Source code & data",
    "contact.sourceBody":
      "This project is open and transparent: the code and data used to build this site are publicly available.",
    "contact.sourceCta": "View the project on GitHub",
    "contact.feedbackHeading": "Feedback & bugs",
    "contact.feedbackBody":
      "For general feedback or to report a technical problem, open an issue on GitHub.",
    "contact.feedbackCta": "Open an issue",

    "footer.about": "About",
    "about.title": "About & methodology",
    "about.intro":
      "This site brings together, in one searchable place, the Quebec physicians who have been the subject of a disciplinary sanction. Its purpose is transparency and the protection of the public.",
    "about.sourceHeading": "Data source",
    "about.sourceBody":
      "All data comes from the public registries of the Collège des médecins du Québec: the physician directory and the disciplinary council decisions. Official text (the charges and the sanctions) is reproduced verbatim, without rewording, and every profile links to the official decision.",
    "about.methodHeading": "How the data is collected",
    "about.methodBody":
      "Information is collected automatically from the CMQ’s public services, then updated each week from the published notices (striking off, practice restriction, suspension, licence revocation). Collection is done at a measured pace and identifies itself honestly.",
    "about.scopeHeading": "What we include",
    "about.scopeBody":
      "We show only physicians who were the subject of a genuine disciplinary finding. Dismissed or withdrawn complaints are never displayed. Administrative strikings off for unpaid dues are not disciplinary sanctions and are excluded.",
    "about.privacyHeading": "Privacy",
    "about.privacyBody":
      "Out of respect for privacy, we show only the practice city; we do not publish any address or phone number. Non-publication orders that protect patients’ identities are respected.",
    "about.accuracyHeading": "Accuracy & limitations",
    "about.accuracyBody":
      "The CMQ registry shows only current sanctions: a temporary striking off that has already been served drops out of it. We recover it from the text of the decision and mark it as served. Some older decisions are available only through an external link.",
    "about.correctionsHeading": "Report an error",
    "about.correctionsBody":
      "We care about accuracy. To report an error or request a correction, contact us.",
    "about.correctionsCta": "Contact us",
    "about.independenceHeading": "Independence",
    "about.independenceBody":
      "This site is independent. It is neither affiliated with nor endorsed by the Collège des médecins du Québec.",
  },
} as const;

export type UiKey = keyof (typeof ui)["fr"];

export function useTranslations(lang: Lang) {
  return function t(key: UiKey): string {
    return (ui[lang] as Record<string, string>)[key] ?? (ui.fr as Record<string, string>)[key];
  };
}
