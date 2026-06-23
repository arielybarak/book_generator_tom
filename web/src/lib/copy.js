/**
 * Central UI copy in both languages. Plain, warm, no jargon (see web/CLAUDE.md).
 * Pick a language object via the i18n provider (lib/i18n.jsx) → useLang().t.
 * Keys must stay identical across `hebrew` and `english`.
 */
export const COPY = {
  hebrew: {
    appName: 'TOM',
    tagline: 'יוצרים ספרי מישוש לילדים',

    steps: ['פתיחה', 'בניית הספר', 'יצירה', 'הורדה'],

    landing: {
      headline: 'הופכים משפט לעמוד שאפשר לגעת בו',
      sub: 'כותבים משפט בעברית, מתארים את הציור — ומקבלים עמוד מוכן להדפסה בתלת־ממד, עם ציור בולט, טקסט וברייל. בלי שום ידע טכני.',
      cta: 'בואו ניצור ספר',
      note: 'מתאים להורים, גננות וכל מי שרוצה לספר סיפור במגע.',
      galleryTitle: 'כך נראה עמוד גמור',
    },

    builder: {
      title: 'בנו את הספר שלכם',
      bookNameLabel: 'איך נקרא לספר?',
      bookNamePlaceholder: 'למשל: עמי ותמי',
      sentenceLabel: 'מה כתוב בעמוד?',
      sentencePlaceholder: 'כתבו משפט קצר בעברית…',
      pictureLabel: 'מה רואים בציור?',
      picturePlaceholder: 'תארו במילה־שתיים, למשל: כלב, בית, פרח',
      addPage: 'הוסיפו עמוד',
      pagesTitle: 'העמודים בספר',
      empty: 'עוד לא הוספתם עמודים',
      generate: 'יוצרים את הספר',
      soundQuestion: 'איך הוגים?',
    },

    generate: {
      working: 'מציירים את העמוד… רגע אחד',
      waking: 'המנוע מתעורר — זה לוקח רגע בפעם הראשונה',
      page: 'עמוד',
      regenerate: 'ציירו מחדש',
      next: 'אהבתי, ממשיכים',
      failed: 'משהו השתבש ביצירת העמוד. אפשר לנסות שוב.',
      noStl: 'הציור מוכן, אך קובץ ההדפסה נכשל. אפשר לצייר מחדש.',
      allReady: 'כל העמודים מוכנים להורדה',
      backToEdit: 'חזרה לעריכה',
      retry: 'נסו שוב',
      elapsed: 'זמן היצירה',
    },

    download: {
      title: 'העמוד מוכן!',
      sub: 'אפשר לסובב את הדגם ולראות איך ייראה במגע, ואז להוריד את הקובץ להדפסה.',
      download: 'הורידו את הקובץ להדפסה',
      printTitle: 'איך מדפיסים?',
      printBody:
        'הקובץ הוא קובץ הדפסה תלת־ממדית (STL). אפשר להדפיס במדפסת תלת־ממד ביתית, או לשלוח לבית דפוס/מעבדת הדפסה תלת־ממדית שיכינו אותו עבורכם.',
      startOver: 'יוצרים ספר חדש',
    },

    common: {
      back: 'חזרה',
      remove: 'מחיקה',
      of: 'מתוך',
      language: 'שפה',
      sec: 'ש׳',
      arrowNext: '←', // RTL: forward points left
      arrowPrev: '→',
      viewer: 'תצוגה תלת־ממדית של העמוד — אפשר לסובב',
    },
  },

  english: {
    appName: 'TOM',
    tagline: 'Create tactile books for blind children',

    steps: ['Start', 'Build', 'Create', 'Download'],

    landing: {
      headline: 'Turn a sentence into a page you can touch',
      sub: 'Write a sentence, describe the picture — and get a 3D-printable page with a raised drawing, text and Braille. No technical knowledge needed.',
      cta: 'Let’s make a book',
      note: 'For parents, teachers and anyone who wants to tell a story by touch.',
      galleryTitle: 'This is what a finished page looks like',
    },

    builder: {
      title: 'Build your book',
      bookNameLabel: 'What’s the book called?',
      bookNamePlaceholder: 'e.g. Hansel and Gretel',
      sentenceLabel: 'What does the page say?',
      sentencePlaceholder: 'Write a short word or sentence…',
      pictureLabel: 'What’s in the picture?',
      picturePlaceholder: 'A word or two, e.g. dog, house, flower',
      addPage: 'Add page',
      pagesTitle: 'Pages in the book',
      empty: 'No pages added yet',
      generate: 'Create the book',
      soundQuestion: 'How is it pronounced?',
    },

    generate: {
      working: 'Drawing the page… one moment',
      waking: 'The engine is warming up — the first time takes a moment',
      page: 'Page',
      regenerate: 'Redraw',
      next: 'Looks great, continue',
      failed: 'Something went wrong creating the page. You can try again.',
      noStl: 'The drawing is ready, but the print file failed. You can redraw.',
      allReady: 'All pages are ready to download',
      backToEdit: 'Back to editing',
      retry: 'Try again',
      elapsed: 'Generation time',
    },

    download: {
      title: 'Your page is ready!',
      sub: 'Rotate the model to see how it feels, then download the print file.',
      download: 'Download the print file',
      printTitle: 'How do I print it?',
      printBody:
        'The file is a 3D print file (STL). Print it on a home 3D printer, or send it to a print shop / 3D-printing lab to make it for you.',
      startOver: 'Create a new book',
    },

    common: {
      back: 'Back',
      remove: 'Remove',
      of: 'of',
      language: 'Language',
      sec: 's',
      arrowNext: '→', // LTR: forward points right
      arrowPrev: '←',
      viewer: '3D preview of the page — you can rotate it',
    },
  },
}
